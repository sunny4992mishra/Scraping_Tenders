/* ============================================================
   CHARDI.AI — SEARCH
   Debounced search bar that drives filter state.
   ============================================================ */

const Search = (() => {
  let debounceTimer = null;
  const DEBOUNCE_MS = 300;

  function init() {
    const input = document.getElementById('search-input');
    const clearBtn = document.querySelector('.search-wrapper__clear');
    if (!input) return;

    // Restore from filter state
    const current = window.Filters.get();
    if (current.q) {
      input.value = current.q;
      clearBtn && clearBtn.classList.add('visible');
    }

    input.addEventListener('input', () => {
      const val = input.value.trim();
      clearBtn && clearBtn.classList.toggle('visible', val.length > 0);

      clearTimeout(debounceTimer);
      debounceTimer = setTimeout(() => {
        window.Filters.set({ q: val });
      }, DEBOUNCE_MS);
    });

    input.addEventListener('keydown', (e) => {
      if (e.key === 'Escape') {
        input.value = '';
        clearBtn && clearBtn.classList.remove('visible');
        clearTimeout(debounceTimer);
        window.Filters.set({ q: '' });
      }
    });

    if (clearBtn) {
      clearBtn.addEventListener('click', () => {
        input.value = '';
        clearBtn.classList.remove('visible');
        clearTimeout(debounceTimer);
        window.Filters.set({ q: '' });
        input.focus();
      });
    }
  }

  return { init };
})();

window.Search = Search;