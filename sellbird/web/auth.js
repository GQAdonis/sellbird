// ── Dashboard authorisation ──
//
// Every API call needs the token `sellbird dashboard` prints. It arrives once,
// in the link's #fragment (browsers never put fragments in HTTP requests or
// Referer, so it stays out of server and proxy logs), is moved to
// sessionStorage (this tab only, gone when it closes) and replaced in the
// address bar before anything else on the page runs. The browser itself
// sees the full link before then, so its history or extensions may too. It is only ever sent as an
// Authorization header, and only to this origin: never a cookie, never a
// query string, never another host.
//
// Gateway mode (SELLBIRD_DASHBOARD_MODE=gateway) is the one exception. There
// is no dashboard token: the operator signs in at the gateway, which checks
// the sign-in cookie on every request and adds its own short-lived token
// before the request reaches Sellbird. So the page sends this origin's
// cookies with its API calls and no Authorization header, and never stores a
// token. The server marks that mode with a <meta> tag in the page.

const AUTH_KEY = 'sellbird-dashboard-token';
// The key under Harvey, Sellbird's old name: a tab open across the update
// keeps its token instead of being signed out.
const LEGACY_AUTH_KEY = 'harvey-dashboard-token';
const AUTH_TOKEN_RE = /^[A-Za-z0-9_-]{43,128}$/;
const MODE_META = 'meta[name="sellbird-dashboard-mode"]';

// True when the server says a gateway signs the operator in.
function gatewayMode() {
  if (typeof document === 'undefined') return false;
  const meta = document.querySelector(MODE_META);
  return !!meta && meta.getAttribute('content') === 'gateway';
}

(function takeFragmentToken() {
  const hash = window.location.hash || '';
  if (!hash) return;
  const token = new URLSearchParams(hash.slice(1)).get('token');
  history.replaceState(null, '', window.location.pathname + window.location.search);
  if (token && AUTH_TOKEN_RE.test(token) && !gatewayMode()) setAuthToken(token);
})();

function authToken() {
  if (gatewayMode()) return '';
  try {
    let token = sessionStorage.getItem(AUTH_KEY);
    if (!token) {
      token = sessionStorage.getItem(LEGACY_AUTH_KEY);
      if (token) { sessionStorage.setItem(AUTH_KEY, token); sessionStorage.removeItem(LEGACY_AUTH_KEY); }
    }
    return token || '';
  } catch { return ''; }
}

function setAuthToken(token) {
  if (gatewayMode() || !AUTH_TOKEN_RE.test(token || '')) return false;
  try { sessionStorage.setItem(AUTH_KEY, token); return true; } catch { return false; }
}

function clearAuthToken() {
  try { sessionStorage.removeItem(AUTH_KEY); } catch { /* ignore */ }
}

// A same-origin URL for an absolute path ("/api/..."), or null.
function sameOriginUrl(path) {
  if (typeof path !== 'string' || !path.startsWith('/') || path.startsWith('//') ||
      path.includes('\\')) return null;
  let url;
  try { url = new URL(path, window.location.origin); } catch { return null; }
  return url.origin === window.location.origin ? url : null;
}

// fetch() for this dashboard's own API, with the token attached (in gateway
// mode: with this origin's cookies and no token). Refuses anything that isn't
// same-origin, and never follows redirects.
function authFetch(path, opts) {
  const url = sameOriginUrl(path);
  if (!url) return Promise.reject(new Error('refusing to send the dashboard token off-origin'));
  const o = Object.assign({}, opts || {});
  const headers = new Headers(o.headers || {});
  const gateway = gatewayMode();
  const token = authToken();
  // The gateway writes Authorization itself; the page must not supply one.
  if (gateway) headers.delete('Authorization');
  else if (token) headers.set('Authorization', 'Bearer ' + token);
  o.headers = headers;
  o.mode = 'same-origin';
  o.credentials = gateway ? 'same-origin' : 'omit';
  o.cache = 'no-store';
  o.redirect = 'error';
  // Not 'no-referrer': per the Fetch spec that makes a POST's Origin "null"
  // (Safari follows it), and the guard then refuses every action.
  o.referrerPolicy = 'same-origin';
  return fetch(url.href, o);
}
