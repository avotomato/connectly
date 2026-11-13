/**
 * Connectly Tracker — educational demo
 * Silently collects behavioural & fingerprint data, just like real social networks do.
 */

// ─── Helpers ────────────────────────────────────────────────────────────────

function send(type, target, value) {
  fetch('/track', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ type, target: String(target), value: String(value ?? '') })
  });
}

function sendFingerprint(data) {
  fetch('/fingerprint', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(data)
  });
}

// ─── Browser / Device Fingerprint ───────────────────────────────────────────

(function collectFingerprint() {
  const fp = {
    browser:           navigator.userAgent,
    language:          navigator.language,
    platform:          navigator.platform,
    screen_resolution: `${screen.width}x${screen.height}`,
    color_depth:       screen.colorDepth + ' bit',
    timezone:          Intl.DateTimeFormat().resolvedOptions().timeZone,
    do_not_track:      navigator.doNotTrack || 'not set',
    cookies_enabled:   navigator.cookieEnabled,
    touch_support:     navigator.maxTouchPoints > 0 ? 'yes' : 'no',
    memory_gb:         navigator.deviceMemory || 'unknown',
    cpu_cores:         navigator.hardwareConcurrency || 'unknown',
    online:            navigator.onLine,
    referrer:          document.referrer || 'direct',
    page_load_time:    Math.round(performance.now()) + ' ms',
  };
  sendFingerprint(fp);
})();

// ─── Post view time tracking ─────────────────────────────────────────────────

const viewTimers = {};

const observer = new IntersectionObserver((entries) => {
  entries.forEach(entry => {
    const id = entry.target.dataset.postId;
    if (!id) return;
    if (entry.isIntersecting) {
      viewTimers[id] = { start: Date.now() };
    } else {
      if (viewTimers[id]) {
        const secs = ((Date.now() - viewTimers[id].start) / 1000).toFixed(1);
        send('view', id, secs);
        delete viewTimers[id];
      }
    }
  });
}, { threshold: 0.5 });

document.querySelectorAll('.post-card').forEach(card => observer.observe(card));

window.addEventListener('beforeunload', () => {
  Object.entries(viewTimers).forEach(([id, t]) => {
    const secs = ((Date.now() - t.start) / 1000).toFixed(1);
    navigator.sendBeacon('/track', JSON.stringify({ type: 'view', target: id, value: secs }));
  });
  const secs = Math.round((Date.now() - sessionStart) / 1000);
  navigator.sendBeacon('/track', JSON.stringify({ type: 'session_time', target: 'feed', value: secs + 's' }));
});

// ─── Scroll depth ────────────────────────────────────────────────────────────

let maxScroll = 0;
window.addEventListener('scroll', () => {
  const docH = document.body.scrollHeight - window.innerHeight;
  if (docH <= 0) return;
  const pct = Math.round((window.scrollY / docH) * 100);
  if (pct > maxScroll + 10) {
    maxScroll = pct;
    send('scroll_depth', 'feed', pct + '%');
  }
});

// ─── Topic sidebar clicks ─────────────────────────────────────────────────────

document.querySelectorAll('.topic-list li').forEach(li => {
  li.addEventListener('click', () => {
    send('topic_click', li.dataset.topic || li.textContent.trim(), '');
  });
});

// ─── Mouse idle ──────────────────────────────────────────────────────────────

let idleTimer = null;
document.addEventListener('mousemove', () => {
  if (idleTimer) clearTimeout(idleTimer);
  idleTimer = setTimeout(() => send('idle', 'feed', '30s'), 30000);
});

// ─── Session time ─────────────────────────────────────────────────────────────

const sessionStart = Date.now();

// ─── Notification polling ─────────────────────────────────────────────────────
// Poll every 30s and update the badge without a full page reload

function refreshNotifBadge() {
  fetch('/notifications/count')
    .then(r => r.json())
    .then(d => {
      const btn   = document.querySelector('.notif-btn');
      if (!btn) return;
      let badge = btn.querySelector('.notif-badge');
      if (d.count > 0) {
        if (!badge) {
          badge = document.createElement('span');
          badge.className = 'notif-badge';
          btn.appendChild(badge);
        }
        badge.textContent = d.count;
      } else if (badge) {
        badge.remove();
      }
    });
}

setInterval(refreshNotifBadge, 30000);
