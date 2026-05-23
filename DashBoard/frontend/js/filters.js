/* ============================================================
   CHARDI.AI — FILTERS STATE MANAGER
   Maintains filter state, syncs with URL, drives re-renders.
   ============================================================ */

const Filters = (() => {
  /* ── State ── */
  let state = {
    q: '',
    status: 'all',
    state: 'all',
    buyer_type: [],
    portal: [],
    min_value: '',
    max_value: '',
    deadline_after: '',
    deadline_before: '',
    sort_by: '',
    sort_dir: 'asc',
    page: 1
  };

  let _onChangeCallback = null;

  /* ── Read from URL on init ── */
  function readFromURL() {
    const params = new URLSearchParams(window.location.search);

    state.q             = params.get('q') || '';
    state.status        = params.get('status') || 'all';
    state.state         = params.get('state') || 'all';
    state.buyer_type    = params.getAll('buyer_type');
    state.portal        = params.getAll('portal');
    state.min_value     = params.get('min_value') || '';
    state.max_value     = params.get('max_value') || '';
    state.deadline_after  = params.get('deadline_after') || '';
    state.deadline_before = params.get('deadline_before') || '';
    state.sort_by       = params.get('sort_by') || '';
    state.sort_dir      = params.get('sort_dir') || 'asc';
    state.page          = parseInt(params.get('page') || '1', 10);
  }

  /* ── Write to URL ── */
  function pushToURL() {
    const params = new URLSearchParams();

    if (state.q)              params.set('q', state.q);
    if (state.status !== 'all') params.set('status', state.status);
    if (state.state !== 'all')  params.set('state', state.state);
    state.buyer_type.forEach(t => params.append('buyer_type', t));
    state.portal.forEach(p => params.append('portal', p));
    if (state.min_value)      params.set('min_value', state.min_value);
    if (state.max_value)      params.set('max_value', state.max_value);
    if (state.deadline_after)  params.set('deadline_after', state.deadline_after);
    if (state.deadline_before) params.set('deadline_before', state.deadline_before);
    if (state.sort_by)        params.set('sort_by', state.sort_by);
    if (state.sort_dir !== 'asc') params.set('sort_dir', state.sort_dir);
    if (state.page > 1)       params.set('page', state.page);

    const qs = params.toString();
    window.history.replaceState(null, '', qs ? `?${qs}` : window.location.pathname);
  }

  /* ── Trigger callback ── */
  function notify() {
    pushToURL();
    if (_onChangeCallback) _onChangeCallback({ ...state });
    updateActiveCount();
  }

  /* ── Update active filter count indicator ── */
  function updateActiveCount() {
    const active = [
      state.q,
      state.status !== 'all' ? state.status : '',
      state.state !== 'all'  ? state.state  : '',
      ...state.buyer_type,
      ...state.portal,
      state.min_value,
      state.max_value,
      state.deadline_after,
      state.deadline_before
    ].filter(Boolean).length;

    const dot = document.querySelector('.filter-active-dot');
    if (dot) dot.style.display = active > 0 ? 'block' : 'none';

    const clearLink = document.querySelector('.sidebar__clear');
    if (clearLink) clearLink.style.opacity = active > 0 ? '1' : '0.4';

    // Update count badge in header
    const countEl = document.getElementById('active-filter-count');
    if (countEl) {
      countEl.textContent = active > 0 ? active : '';
      countEl.style.display = active > 0 ? 'inline-flex' : 'none';
    }
  }

  /* ── Public API ── */
  function get() { return { ...state }; }

  function set(updates) {
    state = { ...state, ...updates, page: 1 }; // reset page on filter change
    notify();
  }

  function setPage(page) {
    state = { ...state, page };
    notify();
  }

  function setSort(column) {
    if (state.sort_by === column) {
      state = { ...state, sort_dir: state.sort_dir === 'asc' ? 'desc' : 'asc' };
    } else {
      state = { ...state, sort_by: column, sort_dir: 'asc' };
    }
    notify();
  }

  function clearAll() {
    state = {
      q: '', status: 'all', state: 'all',
      buyer_type: [], portal: [],
      min_value: '', max_value: '',
      deadline_after: '', deadline_before: '',
      sort_by: '', sort_dir: 'asc', page: 1
    };
    syncUIToState();
    notify();
  }

  function onChange(callback) {
    _onChangeCallback = callback;
  }

  /* ── Sync Filter UI elements to state ── */
  function syncUIToState() {
    // Search input
    const searchInput = document.getElementById('search-input');
    if (searchInput) searchInput.value = state.q;

    // Status pills
    document.querySelectorAll('.status-pill').forEach(pill => {
      pill.classList.toggle('active', pill.dataset.status === state.status);
    });

    // State select (Desktop & Mobile)
    const stateSelects = ['filter-state', 'filter-state-mobile'];
    stateSelects.forEach(id => {
      const el = document.getElementById(id);
      if (el) el.value = state.state;
    });

    // Buyer type checkboxes
    document.querySelectorAll('[data-buyer-type]').forEach(cb => {
      cb.checked = state.buyer_type.includes(cb.dataset.buyerType);
    });

    // Portal checkboxes
    document.querySelectorAll('[data-portal]').forEach(cb => {
      cb.checked = state.portal.includes(cb.dataset.portal);
    });

    // Value range (Desktop & Mobile)
    const valInputs = [
      { id: 'filter-min-value', key: 'min_value' },
      { id: 'filter-max-value', key: 'max_value' },
      { id: 'filter-min-value-mobile', key: 'min_value' },
      { id: 'filter-max-value-mobile', key: 'max_value' }
    ];
    valInputs.forEach(item => {
      const el = document.getElementById(item.id);
      if (el) el.value = state[item.key];
    });

    // Dates (Desktop & Mobile)
    const dateInputs = [
      { id: 'filter-deadline-after', key: 'deadline_after' },
      { id: 'filter-deadline-before', key: 'deadline_before' },
      { id: 'filter-deadline-after-mobile', key: 'deadline_after' },
      { id: 'filter-deadline-before-mobile', key: 'deadline_before' }
    ];
    dateInputs.forEach(item => {
      const el = document.getElementById(item.id);
      if (el) el.value = state[item.key];
    });
  }

  /* ── Bind all filter UI elements ── */
  function bindUI() {
    // Status pills
    document.querySelectorAll('.status-pill').forEach(pill => {
      pill.addEventListener('click', () => {
        document.querySelectorAll('.status-pill').forEach(p => p.classList.remove('active'));
        pill.classList.add('active');
        set({ status: pill.dataset.status });
      });
    });

    // State select (Desktop & Mobile)
    ['filter-state', 'filter-state-mobile'].forEach(id => {
      const el = document.getElementById(id);
      if (el) {
        el.addEventListener('change', () => {
          set({ state: el.value });
        });
      }
    });

    // Buyer type checkboxes
    document.querySelectorAll('[data-buyer-type]').forEach(cb => {
      cb.addEventListener('change', () => {
        const checked = Array.from(document.querySelectorAll(`[data-buyer-type="${cb.dataset.buyerType}"]:checked`));
        // We need to sync all checkboxes of the same type (mobile & desktop)
        const allOfType = document.querySelectorAll(`[data-buyer-type="${cb.dataset.buyerType}"]`);
        allOfType.forEach(el => el.checked = cb.checked);
        
        const finalChecked = Array.from(new Set(
          Array.from(document.querySelectorAll('[data-buyer-type]:checked'))
            .map(el => el.dataset.buyerType)
        ));
        set({ buyer_type: finalChecked });
      });
    });

    // Portal checkboxes
    document.querySelectorAll('[data-portal]').forEach(cb => {
      cb.addEventListener('change', () => {
        const allOfType = document.querySelectorAll(`[data-portal="${cb.dataset.portal}"]`);
        allOfType.forEach(el => el.checked = cb.checked);

        const finalChecked = Array.from(new Set(
          Array.from(document.querySelectorAll('[data-portal]:checked'))
            .map(el => el.dataset.portal)
        ));
        set({ portal: finalChecked });
      });
    });

    // Value range (Desktop & Mobile)
    const valFields = [
      { id: 'filter-min-value', key: 'min_value' },
      { id: 'filter-max-value', key: 'max_value' },
      { id: 'filter-min-value-mobile', key: 'min_value' },
      { id: 'filter-max-value-mobile', key: 'max_value' }
    ];
    valFields.forEach(item => {
      const el = document.getElementById(item.id);
      if (el) {
        el.addEventListener('input', debounce(() => {
          set({ [item.key]: el.value });
        }, 500));
      }
    });

    // Date range (Desktop & Mobile)
    const dateFields = [
      { id: 'filter-deadline-after', key: 'deadline_after' },
      { id: 'filter-deadline-before', key: 'deadline_before' },
      { id: 'filter-deadline-after-mobile', key: 'deadline_after' },
      { id: 'filter-deadline-before-mobile', key: 'deadline_before' }
    ];
    dateFields.forEach(item => {
      const el = document.getElementById(item.id);
      if (el) {
        el.addEventListener('change', () => {
          set({ [item.key]: el.value });
        });
      }
    });

    // Clear all
    const clearLink = document.querySelector('.sidebar__clear');
    if (clearLink) {
      clearLink.addEventListener('click', (e) => {
        e.preventDefault();
        clearAll();
      });
    }

    // Mobile drawer
    const filterToggle = document.getElementById('filter-toggle');
    const sidebarOverlay = document.getElementById('sidebar-overlay');
    const sidebarDrawer  = document.getElementById('sidebar-drawer');
    const sidebarClose   = document.getElementById('sidebar-close');

    if (filterToggle && sidebarDrawer) {
      filterToggle.addEventListener('click', () => {
        sidebarDrawer.classList.add('open');
        sidebarOverlay && sidebarOverlay.classList.add('active');
        document.body.style.overflow = 'hidden';
      });
    }

    function closeDrawer() {
      if (sidebarDrawer) sidebarDrawer.classList.remove('open');
      if (sidebarOverlay) sidebarOverlay.classList.remove('active');
      document.body.style.overflow = '';
    }

    if (sidebarOverlay) sidebarOverlay.addEventListener('click', closeDrawer);
    if (sidebarClose)   sidebarClose.addEventListener('click', closeDrawer);

    // Initialize UI state from loaded state
    syncUIToState();
    updateActiveCount();
  }

  /* ── Debounce utility ── */
  function debounce(fn, ms) {
    let timer;
    return function(...args) {
      clearTimeout(timer);
      timer = setTimeout(() => fn.apply(this, args), ms);
    };
  }

  /* ── Init ── */
  function init() {
    readFromURL();
  }

  return { init, get, set, setPage, setSort, clearAll, onChange, bindUI, syncUIToState };
})();

window.Filters = Filters;