import { useCallback, useEffect, useRef, useState } from "react";
import { ago, api, detectBrowserApp, detectDevice } from "../api";
import { Badge } from "../components/Badge";

function mapRect(x, y, w, h, fw, fh, cw, ch) {
  const scale = Math.min(cw / fw, ch / fh);
  const dw = fw * scale;
  const dh = fh * scale;
  const ox = (cw - dw) / 2;
  const oy = (ch - dh) / 2;
  const mx = fw - x - w;
  return { x: ox + mx * scale, y: oy + y * scale, w: w * scale, h: h * scale };
}

export default function Desk() {
  const videoRef = useRef(null);
  const overlayRef = useRef(null);
  const wrapRef = useRef(null);
  const streamRef = useRef(null);
  const meRef = useRef(null);
  const lastInput = useRef(Date.now());
  const lastPingAt = useRef(Date.now());
  const lastPresent = useRef(null);
  const lastMarks = useRef([]);
  const lastSize = useRef({ w: 640, h: 480 });
  const camTried = useRef(false);

  const [me, setMe] = useState(null);
  const [camOn, setCamOn] = useState(false);
  const [emptyMsg, setEmptyMsg] = useState("Clock in — Chrome will ask to use your camera. Allow it.");
  const [face, setFace] = useState({ enrolled: false, count: 0, needed: 5 });
  const [faceMsg, setFaceMsg] = useState("");
  const [enrolling, setEnrolling] = useState(false);
  const [cameras, setCameras] = useState([]);
  const [cameraId, setCameraId] = useState(() => localStorage.getItem("desktrack_camera_id") || "");
  const cameraIdRef = useRef(cameraId);
  cameraIdRef.current = cameraId;



  const showCam = useCallback((on) => {
    setCamOn(on);
  }, []);

  const stopCamera = useCallback(() => {
    if (streamRef.current) {
      streamRef.current.getTracks().forEach((t) => t.stop());
      streamRef.current = null;
    }
    if (videoRef.current) videoRef.current.srcObject = null;
    showCam(false);
    const overlay = overlayRef.current;
    if (overlay) {
      const ctx = overlay.getContext("2d");
      ctx.clearRect(0, 0, overlay.width, overlay.height);
    }
  }, [showCam]);

  const drawOverlay = useCallback((present) => {
    const overlay = overlayRef.current;
    const wrap = wrapRef.current;
    const video = videoRef.current;
    if (!overlay || !wrap) return;
    overlay.width = wrap.clientWidth;
    overlay.height = wrap.clientHeight;
    const ctx = overlay.getContext("2d");
    ctx.clearRect(0, 0, overlay.width, overlay.height);
    if (!streamRef.current) return;
    const fw = lastSize.current.w || video?.videoWidth || 640;
    const fh = lastSize.current.h || video?.videoHeight || 480;
    const zone = mapRect(fw * 0.08, fh * 0.04, fw * 0.84, fh * 0.94, fw, fh, overlay.width, overlay.height);
    ctx.strokeStyle = "#22c55e";
    ctx.lineWidth = 3;
    ctx.strokeRect(zone.x, zone.y, zone.w, zone.h);
    lastMarks.current.forEach((m) => {
      const r = mapRect(m.x, m.y, m.w, m.h, fw, fh, overlay.width, overlay.height);
      ctx.strokeStyle = m.at_desk ? "#ef4444" : "#3b82f6";
      ctx.lineWidth = 3;
      ctx.strokeRect(r.x, r.y, r.w, r.h);
      ctx.font = "600 14px Segoe UI, sans-serif";
      ctx.fillStyle = m.at_desk ? "#ef4444" : "#3b82f6";
      ctx.fillText(m.at_desk ? (m.label || "You") : m.label || "Other", r.x, Math.max(18, r.y - 6));
    });
    ctx.font = "600 18px Segoe UI, sans-serif";
    ctx.fillStyle = present ? "#22c55e" : "#ef4444";
    ctx.fillText(present ? "Status: PRESENT" : "Status: ABSENT", 16, 32);
  }, []);

  const refreshCameraList = useCallback(async () => {
    if (!navigator.mediaDevices?.enumerateDevices) return [];
    const all = await navigator.mediaDevices.enumerateDevices();
    const cams = all.filter((d) => d.kind === "videoinput" && d.deviceId);
    setCameras(cams);
    return cams;
  }, []);

  const startCamera = useCallback(
    async (forceDeviceId) => {
      if (!navigator.mediaDevices?.getUserMedia) {
        const insecure = typeof window !== "undefined" && !window.isSecureContext;
        setEmptyMsg(
          insecure
            ? "Camera needs HTTPS (or localhost). Open DeskTrack over https://… — plain http://IP blocks the camera in Chrome."
            : "This browser cannot use the camera. Try Chrome or Edge."
        );
        showCam(false);
        return false;
      }
      if (streamRef.current) {
        streamRef.current.getTracks().forEach((t) => t.stop());
        streamRef.current = null;
      }
      if (videoRef.current) videoRef.current.srcObject = null;

      const wantId = forceDeviceId || cameraIdRef.current || "";
      const tryOpen = (video) => navigator.mediaDevices.getUserMedia({ video, audio: false });

      // Virtual cams (OBS etc.) often reject width/height — try bare deviceId first
      const attempts = [];
      if (wantId) {
        attempts.push({ deviceId: { exact: wantId } });
        attempts.push({ deviceId: { exact: wantId }, width: { ideal: 640 }, height: { ideal: 360 } });
        attempts.push({ deviceId: { ideal: wantId } });
      }
      attempts.push(true); // any camera
      attempts.push({ width: { ideal: 640 }, height: { ideal: 360 } });

      let stream = null;
      let lastErr = null;
      for (const video of attempts) {
        try {
          stream = await tryOpen(video);
          break;
        } catch (err) {
          lastErr = err;
          stream = null;
        }
      }

      if (!stream) {
        showCam(false);
        if (lastErr?.name === "NotAllowedError") {
          setEmptyMsg(
            "Camera was blocked. Click the camera icon in the address bar and allow access, then Clock in again."
          );
          alert("Please Allow camera access for this site, then click Clock in again.");
        } else {
          setEmptyMsg(
            "Could not open that camera. In OBS click Start Virtual Camera, close other apps using it, then Refresh list and try again."
          );
        }
        return false;
      }

      try {
        streamRef.current = stream;
        const cams = await refreshCameraList();
        const activeId = stream.getVideoTracks()[0]?.getSettings?.()?.deviceId || "";
        const activeLabel = cams.find((c) => c.deviceId === activeId)?.label || "";
        if (activeId) {
          setCameraId(activeId);
          cameraIdRef.current = activeId;
          localStorage.setItem("desktrack_camera_id", activeId);
        }
        if (videoRef.current) {
          videoRef.current.srcObject = stream;
          await videoRef.current.play();
        }
        showCam(true);
        if (wantId && activeId && wantId !== activeId) {
          setEmptyMsg(
            `Could not open the selected camera — using ${activeLabel || "another camera"} instead. Start OBS Virtual Camera, then pick it again.`
          );
        } else {
          setEmptyMsg("Camera is on.");
        }
        return true;
      } catch (err) {
        stream.getTracks().forEach((t) => t.stop());
        streamRef.current = null;
        showCam(false);
        setEmptyMsg("Camera opened but could not play. Try Refresh list or another camera.");
        return false;
      }
    },
    [showCam, refreshCameraList]
  );

  async function onCameraChange(e) {
    const id = e.target.value;
    setCameraId(id);
    cameraIdRef.current = id;
    localStorage.setItem("desktrack_camera_id", id);
    camTried.current = true;
    await startCamera(id);
  }

  async function refreshCamerasClick() {
    // Re-list after user starts OBS/virtual cam — Chrome only sees devices that exist at allow-time
    const cams = await refreshCameraList();
    if (!cams.length) {
      await startCamera();
      return;
    }
    setFaceMsg("");
    if (cameraIdRef.current && cams.some((c) => c.deviceId === cameraIdRef.current)) {
      await startCamera(cameraIdRef.current);
    }
  }

  const refreshFace = useCallback(async () => {
    const { ok, data } = await api("/api/me/face");
    if (ok) setFace(data);
  }, []);

  const refresh = useCallback(async () => {
    const { ok, data } = await api("/api/me");
    if (!ok) return;
    meRef.current = data;
    setMe(data);
    if (data.clocked_in && !streamRef.current && !camTried.current) {
      camTried.current = true;
      startCamera();
    }
    if (!data.clocked_in && streamRef.current) stopCamera();
    if (!data.clocked_in) {
      setEmptyMsg("Clock in — Chrome will ask to use your camera. Allow it.");
    }
  }, [startCamera, stopCamera]);

  async function enrollFaceOnce() {
    const video = videoRef.current;
    if (!streamRef.current || !video || video.readyState < 2) {
      const cam = await startCamera();
      if (!cam) {
        setFaceMsg("Allow the camera first, then enroll.");
        return;
      }
      await new Promise((r) => setTimeout(r, 600));
    }
    setEnrolling(true);
    setFaceMsg("Hold still — capturing your face…");
    try {
      for (let i = 0; i < 8; i++) {
        const v = videoRef.current;
        if (!v || v.readyState < 2) break;
        const shot = document.createElement("canvas");
        shot.width = v.videoWidth || 480;
        shot.height = v.videoHeight || 360;
        shot.getContext("2d").drawImage(v, 0, 0, shot.width, shot.height);
        const image = shot.toDataURL("image/jpeg", 0.7).split(",")[1];
        const { ok, data } = await api("/api/me/face/enroll", {
          method: "POST",
          body: JSON.stringify({ image }),
        });
        if (!ok) {
          setFaceMsg(data.error || "Could not enroll. Face the camera.");
          break;
        }
        setFace({
          enrolled: !!data.ready,
          count: data.count || 0,
          needed: data.needed ?? 0,
        });
        setFaceMsg(data.message || "Saved.");
        if (data.ready) {
          window.dispatchEvent(new Event("desktrack-face"));
          break;
        }
        await new Promise((r) => setTimeout(r, 350));
      }
      await refreshFace();
      window.dispatchEvent(new Event("desktrack-face"));
    } finally {
      setEnrolling(false);
    }
  }

  async function clearFace() {
    if (!confirm("Remove your enrolled face? Presence will not be identity-checked until you enroll again.")) return;
    await api("/api/me/face", { method: "DELETE", body: "{}" });
    setFaceMsg("Face enrollment cleared.");
    refreshFace();
    window.dispatchEvent(new Event("desktrack-face"));
  }

  async function toggleClock() {
    const goingOut = !!meRef.current?.clocked_in;
    if (goingOut) {
      const { ok, data } = await api("/api/clock", {
        method: "POST",
        body: JSON.stringify({ action: "out" }),
      });
      if (!ok) {
        alert(data.error || "Could not update.");
        return;
      }
      stopCamera();
      camTried.current = false;
      await refresh();
      return;
    }
    const cam = await startCamera();
    if (!cam) return;
    const { ok, data } = await api("/api/clock", {
      method: "POST",
      body: JSON.stringify({ action: "in" }),
    });
    if (!ok) {
      alert(data.error || "Could not update.");
      stopCamera();
      return;
    }
    await refresh();
  }

  useEffect(() => {
    const bump = () => {
      lastInput.current = Date.now();
    };
    ["mousemove", "keydown", "click", "scroll"].forEach((ev) =>
      window.addEventListener(ev, bump, { passive: true })
    );
    const onVisible = () => {
      const gap = Math.floor((Date.now() - lastPingAt.current) / 1000);
      if (gap > 30) {
        lastInput.current = Date.now() - gap * 1000;
      } else {
        lastInput.current = Date.now();
      }
    };
    const onVisibility = () => {
      if (document.visibilityState === "visible") onVisible();
    };
    document.addEventListener("visibilitychange", onVisibility);
    window.addEventListener("focus", onVisible);
    const onHide = () => stopCamera();
    window.addEventListener("pagehide", onHide);
    refresh();
    refreshFace();
    const t1 = setInterval(refresh, 3000);
    const t2 = setInterval(async () => {
      const video = videoRef.current;
      if (!streamRef.current || !meRef.current?.clocked_in || !video || video.readyState < 2) return;
      const shot = document.createElement("canvas");
      shot.width = video.videoWidth || 640;
      shot.height = video.videoHeight || 480;
      shot.getContext("2d").drawImage(video, 0, 0, shot.width, shot.height);
      const image = shot.toDataURL("image/jpeg", 0.55).split(",")[1];
      try {
        const { data } = await api("/api/me/track", {
          method: "POST",
          body: JSON.stringify({
            image,
            idle_seconds: 0,
            app: detectBrowserApp(),
            window_title: document.title,
            device: detectDevice(),
          }),
        });
        lastPingAt.current = Date.now();
        if (data.present !== undefined) lastPresent.current = !!data.present;
        if (data.marks) lastMarks.current = data.marks;
        if (data.skipped === "dark_frame") lastMarks.current = [];
        if (data.width && data.height) lastSize.current = { w: data.width, h: data.height };
        if (data.today) {
          setMe((prev) => (prev ? { ...prev, today: { ...prev.today, ...data.today }, present: data.present ? 1 : 0 } : prev));
        }
      } catch {
        /* keep the live view even if one ping fails */
      }
      drawOverlay(lastPresent.current);
    }, 2000);
    const t3 = setInterval(() => drawOverlay(lastPresent.current), 300);
    return () => {
      ["mousemove", "keydown", "click", "scroll"].forEach((ev) => window.removeEventListener(ev, bump));
      document.removeEventListener("visibilitychange", onVisibility);
      window.removeEventListener("focus", onVisible);
      window.removeEventListener("pagehide", onHide);
      clearInterval(t1);
      clearInterval(t2);
      clearInterval(t3);
      stopCamera();
    };
  }, [refresh, refreshFace, stopCamera, drawOverlay]);

  function toggleFullscreen() {
    const wrap = wrapRef.current;
    if (!wrap) return;
    if (!document.fullscreenElement) {
      (wrap.requestFullscreen || wrap.webkitRequestFullscreen).call(wrap);
    } else {
      (document.exitFullscreen || document.webkitExitFullscreen).call(document);
    }
  }

  const p = me;
  const today = p?.today || {};
  const present = p?.present === 1 ? "yes" : p?.present === 0 ? "no" : "unknown";
  const seatClass = p?.present === 1 ? "yes" : p?.present === 0 ? "no" : "";

  let callout = "Clocked out. Click Clock in — the browser will ask to use your camera. Click Allow.";
  let calloutOk = false;
  if (p?.clocked_in && camOn) {
    callout = p?.agent_apps
      ? "Camera is on for face/presence. Windows agent is sending desktop apps. Keep this tab open."
      : "Camera is on. Keep this tab open while you work. Clock out to turn it off. Video is not saved.";
    calloutOk = true;
  } else if (p?.clocked_in) {
    callout = "You are clocked in. Click Clock in again if the camera is not showing, and Allow access.";
  }

  return (
    <>
      <header className="page">
        <h1>My desk</h1>
        <div className="actions">
          <button type="button" onClick={toggleClock}>
            {p?.clocked_in ? "Clock out" : "Clock in"}
          </button>
        </div>
      </header>
      <div className={calloutOk ? "callout ok" : "callout"}>{callout}</div>
      {!face.enrolled ? (
        <>
          <div className="callout face-needed">
            <strong>Face enrollment required.</strong> Click <em>Enroll face</em> below, allow the camera,
            and look at the screen until it says enrolled. Only your face will count as present.
          </div>
          <div className="card face-card">
            <h2>Your face (identity)</h2>
            <p className="hint">
              Enroll once so only <strong>you</strong> count as present. Someone else at your desk will not count.
            </p>
            <p className="face-status">
              Not enrolled yet — need about {face.needed || 5} face samples.
            </p>
            {faceMsg ? <p className="hint">{faceMsg}</p> : null}
            <div className="actions">
              <button type="button" onClick={enrollFaceOnce} disabled={enrolling}>
                {enrolling ? "Enrolling…" : "Enroll face"}
              </button>
            </div>
          </div>
        </>
      ) : (
        <div className="callout ok face-done">
          Face enrolled — identity check is on.
          <button type="button" className="linkish" onClick={clearFace}>
            Clear &amp; re-enroll
          </button>
        </div>
      )}
      <div className="kpis">
        <div className="kpi">
          <span>Status</span>
          <strong>
            <Badge status={p?.status} />
          </strong>
        </div>
        <div className="kpi">
          <span>Seated</span>
          <strong>{today.seated || "—"}</strong>
        </div>
        <div className="kpi">
          <span>Active</span>
          <strong>{today.active || "—"}</strong>
        </div>
        <div className="kpi">
          <span>Break left</span>
          <strong>{today.break_left || "30m"}</strong>
        </div>
        <div className="kpi">
          <span>Sleep today</span>
          <strong>{today.idle || "—"}</strong>
        </div>
      </div>
      <div className="desk-grid">
        <section className="monitor-card card">
          <div className="monitor-head">
            <h2>Live monitoring</h2>
            <div className="cam-pick-row">
              <label className="cam-pick">
                Camera
                <select value={cameraId} onChange={onCameraChange} disabled={!cameras.length && !camOn}>
                  {!cameras.length ? <option value="">Allow camera to list devices…</option> : null}
                  {cameras.map((c, i) => (
                    <option key={c.deviceId} value={c.deviceId}>
                      {c.label || `Camera ${i + 1}`}
                    </option>
                  ))}
                </select>
              </label>
              <button type="button" className="ghost cam-refresh" onClick={refreshCamerasClick}>
                Refresh list
              </button>
            </div>
          </div>
          <p className="hint cam-hint">
            If OBS is listed but won’t open: in OBS click <strong>Start Virtual Camera</strong>, close Zoom/Teams/Camera
            app if open, then click <em>Refresh list</em> and select OBS again. Virtual cams often fail if resolution is
            forced — DeskTrack now opens them without that.
          </p>
          <div className="video-wrap" ref={wrapRef} title="Click for fullscreen" onClick={toggleFullscreen}>
            <video ref={videoRef} className={camOn ? "on" : ""} autoPlay playsInline muted />
            <canvas ref={overlayRef} />
            {!camOn ? <p className="muted">{emptyMsg}</p> : null}
            <span className="fs-hint">Click for fullscreen</span>
          </div>
          <p className="legend">
            <span className="leg">
              <span className="dot green" />
              Desk zone
            </span>
            <span className="leg">
              <span className="dot red" />
              At desk
            </span>
            <span className="leg">
              <span className="dot blue" />
              Outside
            </span>
            <span className="leg hint">Click for fullscreen</span>
          </p>
        </section>
        <div className="side">
          <article className="card now-card">
            <h2>Right now</h2>
            <div className="now-grid">
              <div className="now-row">
                <span>In seat</span>
                <b className={`seat ${seatClass}`}>{present}</b>
              </div>
              <div className="now-row">
                <span>Device</span>
                <b>{p?.device || "—"}</b>
              </div>
              <div className="now-row">
                <span>App</span>
                <b title={p?.app || ""}>{p?.app || "—"}</b>
              </div>
              <div className="now-row">
                <span>PC</span>
                <b>{p?.status === "inactive" ? "sleep/offline" : "awake"}</b>
              </div>
            </div>
            <p className="now-title" title={p?.window_title || ""}>
              {p?.window_title || "No window title"}
            </p>
            <p className="now-ago">{ago(p?.updated)}</p>
          </article>
          <article className="card apps-card">
            <h2>Apps today</h2>
            <p className="hint apps-hint">
              Desktop apps come from the Windows agent. Face and presence come from this browser camera.
            </p>
            <ul className="apps">
              {(today.apps || []).length ? (
                today.apps.map((a) => (
                  <li key={a.app}>
                    <span>{a.app}</span>
                    <span>{a.label}</span>
                  </li>
                ))
              ) : (
                <li>No samples yet.</li>
              )}
            </ul>
          </article>
        </div>
      </div>
    </>
  );
}
