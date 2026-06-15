/**
 * Green Curve — Client Auth Library
 * Loaded on every page. Exposes window.gcAuth.
 * Token stored in localStorage as 'gc_auth_token'.
 * User info stored as 'gc_auth_user' (JSON).
 */

(function () {
  const TOKEN_KEY = 'gc_auth_token';
  const USER_KEY  = 'gc_auth_user';

  function _apiBase() {
    return localStorage.getItem('gc_api_base') || '';
  }

  async function _post(path, body) {
    const res = await fetch(_apiBase() + path, {
      method:  'POST',
      headers: { 'Content-Type': 'application/json' },
      body:    JSON.stringify(body),
    });
    const data = await res.json().catch(() => ({}));
    if (!res.ok) throw new Error(data.detail || data.message || 'Request failed');
    return data;
  }

  async function _authed(method, path, body) {
    const token = localStorage.getItem(TOKEN_KEY);
    const headers = { 'Content-Type': 'application/json' };
    if (token) headers['Authorization'] = 'Bearer ' + token;
    const opts = { method, headers };
    if (body !== undefined) opts.body = JSON.stringify(body);
    const res = await fetch(_apiBase() + path, opts);
    if (res.status === 401) {
      gcAuth.logout();
      return null;
    }
    const data = await res.json().catch(() => ({}));
    if (!res.ok) throw new Error(data.detail || data.message || 'Request failed');
    return data;
  }

  function _saveSession(token, user) {
    localStorage.setItem(TOKEN_KEY, token);
    localStorage.setItem(USER_KEY, JSON.stringify(user));
  }

  const gcAuth = {

    // ── Core session ───────────────────────────────────────────────────────
    getToken() { return localStorage.getItem(TOKEN_KEY); },
    getUser()  {
      try { return JSON.parse(localStorage.getItem(USER_KEY) || 'null'); }
      catch { return null; }
    },
    isLoggedIn() { return !!this.getToken(); },

    logout() {
      localStorage.removeItem(TOKEN_KEY);
      localStorage.removeItem(USER_KEY);
      location.href = '/login';
    },

    // ── Auth calls ─────────────────────────────────────────────────────────
    async login(email, password) {
      const data = await _post('/api/auth/login', { email, password });
      _saveSession(data.token, data.user);
      return data.user;
    },

    async register(email, name, org, password) {
      const data = await _post('/api/auth/register', { email, name, org, password });
      _saveSession(data.token, data.user);
      return data.user;
    },

    async me() {
      const data = await _authed('GET', '/api/auth/me');
      if (data) {
        localStorage.setItem(USER_KEY, JSON.stringify(data.user));
        return data.user;
      }
      return null;
    },

    // ── Watchlist ─────────────────────────────────────────────────────────
    async getWatchlist() {
      const data = await _authed('GET', '/api/user/watchlist');
      return data ? data.watchlist : [];
    },

    async addToWatchlist(companyName) {
      return _authed('POST', '/api/user/watchlist', { company_name: companyName });
    },

    async removeFromWatchlist(companyName) {
      return _authed('DELETE', '/api/user/watchlist/' + encodeURIComponent(companyName));
    },

    // ── Watchlist snapshots ────────────────────────────────────────────────
    async getSnapshots() {
      const data = await _authed('GET', '/api/user/watchlist/snapshots');
      return data ? data.snapshots : {};
    },

    async saveSnapshot(companyName, snapshotData) {
      return _authed('POST', '/api/user/watchlist/snapshots', {
        company_name:  companyName,
        snapshot_data: snapshotData,
      });
    },

    // ── Watchlist prefs ────────────────────────────────────────────────────
    async getPrefs() {
      const data = await _authed('GET', '/api/user/watchlist/prefs');
      return data ? data.prefs : { tier_change: true, high_risk: true };
    },

    async savePrefs(prefs) {
      return _authed('PUT', '/api/user/watchlist/prefs', { prefs });
    },

    // ── CAP progress ───────────────────────────────────────────────────────
    async getCAP() {
      const data = await _authed('GET', '/api/user/cap');
      return data ? data.cap : {};
    },

    async updateCAP(companyName, recId, fields) {
      return _authed(
        'PUT',
        '/api/user/cap/' + encodeURIComponent(companyName) + '/' + encodeURIComponent(recId),
        fields
      );
    },
  };

  window.gcAuth = gcAuth;
})();
