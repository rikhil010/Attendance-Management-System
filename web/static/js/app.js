/* ==========================================================================
   GWASOAT shared UI helpers — GW namespace
   - GW.toast(message, type, opts)   professional non-blocking notifications
   - GW.confirm(opts) -> Promise     replaces window.confirm
   - GW.prompt(opts) -> Promise      replaces window.prompt
   - GW.enhanceTable(selector, opts) search + sort + empty state
   - GW.btnLoading(btn, on)          inline spinner on buttons
   ========================================================================== */
(function (w) {
    'use strict';

    var GW = {};

    // ---- Toasts -----------------------------------------------------------
    var ICONS = { success: '\u2713', danger: '\u2715', warning: '!', info: 'i' };
    var TITLES = { success: 'Success', danger: 'Error', warning: 'Warning', info: 'Info' };

    function container() {
        var c = document.getElementById('gw-toast-container');
        if (!c) {
            c = document.createElement('div');
            c.id = 'gw-toast-container';
            document.body.appendChild(c);
        }
        return c;
    }

    GW.toast = function (message, type, opts) {
        type = type || 'info';
        opts = opts || {};
        var el = document.createElement('div');
        el.className = 'gw-toast gw-' + type;

        var icon = document.createElement('span');
        icon.className = 'gw-toast-icon';
        icon.textContent = ICONS[type] || 'i';

        var body = document.createElement('div');
        body.className = 'gw-toast-body';
        var title = document.createElement('div');
        title.className = 'gw-toast-title';
        title.textContent = opts.title || TITLES[type] || 'Notice';
        var msg = document.createElement('div');
        msg.className = 'gw-toast-msg';
        msg.textContent = message || '';
        body.appendChild(title);
        body.appendChild(msg);

        var close = document.createElement('button');
        close.className = 'gw-toast-close';
        close.innerHTML = '&times;';

        el.appendChild(icon);
        el.appendChild(body);
        el.appendChild(close);
        container().appendChild(el);

        requestAnimationFrame(function () { el.classList.add('gw-show'); });

        var timer;
        function dismiss() {
            clearTimeout(timer);
            el.classList.remove('gw-show');
            el.classList.add('gw-hide');
            setTimeout(function () { if (el.parentNode) el.parentNode.removeChild(el); }, 220);
        }
        close.addEventListener('click', dismiss);
        var dur = opts.duration === undefined ? (type === 'danger' ? 6000 : 3500) : opts.duration;
        if (dur > 0) timer = setTimeout(dismiss, dur);
        return { dismiss: dismiss };
    };

    // ---- Dialog (confirm / prompt) ---------------------------------------
    function buildDialog(opts, withInput) {
        return new Promise(function (resolve) {
            var backdrop = document.createElement('div');
            backdrop.className = 'gw-dialog-backdrop';

            var dialog = document.createElement('div');
            dialog.className = 'gw-dialog';

            var h = document.createElement('h5');
            h.textContent = opts.title || (withInput ? 'Enter value' : 'Confirm');
            dialog.appendChild(h);

            if (opts.message) {
                var p = document.createElement('p');
                p.textContent = opts.message;
                dialog.appendChild(p);
            }

            var input;
            if (withInput) {
                input = document.createElement('input');
                input.className = 'form-control';
                input.placeholder = opts.placeholder || '';
                input.value = opts.value || '';
                dialog.appendChild(input);
            }

            var actions = document.createElement('div');
            actions.className = 'gw-dialog-actions';
            var cancel = document.createElement('button');
            cancel.className = 'btn btn-outline-secondary btn-sm';
            cancel.textContent = opts.cancelText || 'Cancel';
            var ok = document.createElement('button');
            ok.className = 'btn btn-sm ' + (opts.danger ? 'btn-danger' : 'btn-primary');
            ok.textContent = opts.okText || (withInput ? 'Save' : 'Confirm');
            actions.appendChild(cancel);
            actions.appendChild(ok);
            dialog.appendChild(actions);

            backdrop.appendChild(dialog);
            document.body.appendChild(backdrop);
            requestAnimationFrame(function () { backdrop.classList.add('gw-show'); });
            if (input) input.focus(); else ok.focus();

            function close(result) {
                backdrop.classList.remove('gw-show');
                setTimeout(function () { if (backdrop.parentNode) backdrop.parentNode.removeChild(backdrop); }, 160);
                resolve(result);
            }
            cancel.addEventListener('click', function () { close(withInput ? null : false); });
            ok.addEventListener('click', function () { close(withInput ? input.value : true); });
            backdrop.addEventListener('click', function (e) { if (e.target === backdrop) close(withInput ? null : false); });
            document.addEventListener('keydown', function esc(e) {
                if (e.key === 'Escape') { close(withInput ? null : false); document.removeEventListener('keydown', esc); }
                if (e.key === 'Enter') { close(withInput ? input.value : true); document.removeEventListener('keydown', esc); }
            });
        });
    }

    GW.confirm = function (opts) {
        if (typeof opts === 'string') opts = { message: opts };
        return buildDialog(opts || {}, false);
    };
    GW.prompt = function (opts) {
        if (typeof opts === 'string') opts = { message: opts };
        return buildDialog(opts || {}, true);
    };

    // ---- Button loading state --------------------------------------------
    GW.btnLoading = function (btn, on, loadingText) {
        if (typeof btn === 'string') btn = document.querySelector(btn);
        else if (btn && btn.jquery) btn = btn[0];
        if (!btn) return;
        if (on) {
            btn.dataset.gwOrig = btn.innerHTML;
            btn.disabled = true;
            btn.innerHTML = '<span class="gw-btn-spinner"></span>' + (loadingText || 'Working...');
        } else {
            if (btn.dataset.gwOrig !== undefined) btn.innerHTML = btn.dataset.gwOrig;
            btn.disabled = false;
        }
    };

    // ---- Table enhancer (search + sort + empty state) --------------------
    // Call AFTER you fill <tbody>. Re-call after refilling.
    GW.enhanceTable = function (table, opts) {
        table = (table.jquery) ? table[0] : (typeof table === 'string' ? document.querySelector(table) : table);
        if (!table) return;
        opts = opts || {};
        var tbody = table.tBodies[0];
        if (!tbody) return;
        var headers = table.tHead ? table.tHead.rows[0].cells : [];

        // Sorting
        if (opts.sortable !== false) {
            Array.prototype.forEach.call(headers, function (th, idx) {
                if (th.dataset.gwNoSort !== undefined) return;
                if (th.dataset.gwBound) return;
                th.dataset.gwBound = '1';
                th.classList.add('gw-sortable');
                if (!th.querySelector('.gw-sort-ind')) {
                    var ind = document.createElement('span');
                    ind.className = 'gw-sort-ind';
                    ind.textContent = '\u2195';
                    th.appendChild(ind);
                }
                th.addEventListener('click', function () { sortBy(idx, th); });
            });
        }

        function sortBy(idx, th) {
            var asc = !th.classList.contains('gw-sort-asc');
            Array.prototype.forEach.call(headers, function (h) { h.classList.remove('gw-sort-asc', 'gw-sort-desc'); });
            th.classList.add(asc ? 'gw-sort-asc' : 'gw-sort-desc');
            var rows = Array.prototype.slice.call(tbody.rows).filter(function (r) { return !r.dataset.gwEmpty; });
            rows.sort(function (a, b) {
                var x = (a.cells[idx] ? a.cells[idx].textContent : '').trim();
                var y = (b.cells[idx] ? b.cells[idx].textContent : '').trim();
                var nx = parseFloat(x), ny = parseFloat(y);
                if (!isNaN(nx) && !isNaN(ny)) return asc ? nx - ny : ny - nx;
                return asc ? x.localeCompare(y) : y.localeCompare(x);
            });
            rows.forEach(function (r) { tbody.appendChild(r); });
        }

        // Search (if a toolbar input is wired by data-gw-search="#id")
        if (opts.search) {
            var input = typeof opts.search === 'string' ? document.querySelector(opts.search) : opts.search;
            if (input && !input.dataset.gwBound) {
                input.dataset.gwBound = '1';
                input.addEventListener('input', function () {
                    var q = input.value.toLowerCase();
                    var visible = 0;
                    Array.prototype.forEach.call(tbody.rows, function (r) {
                        if (r.dataset.gwEmpty) return;
                        var match = r.textContent.toLowerCase().indexOf(q) !== -1;
                        r.style.display = match ? '' : 'none';
                        if (match) visible++;
                    });
                    if (opts.countEl) {
                        var c = typeof opts.countEl === 'string' ? document.querySelector(opts.countEl) : opts.countEl;
                        if (c) c.textContent = visible + ' shown';
                    }
                });
            }
        }
    };

    w.GW = GW;
})(window);
