"""Đánh giá Task QA cho Leader (tab /leader-eval) — bộ lọc + chấm điểm/đánh
giá hàng loạt, lưu trực tiếp lên Jira (2 field LEADER_EVAL_NUM/TEXT).

Tách từ render/__init__.py (issue #110 / #86, A7 — bước cuối Phần A, xoá vỏ
render.py cũ). Zero behavior change — chỉ di chuyển định nghĩa, re-export ở
__init__ để chỗ gọi (qa_dashboard.py) không phải đổi import.
"""
from issues import (i_assignee, i_assignee_name, i_summary, esc, status_class,
                    issue_link)
from render.shell import _document_v2


def render_leader_eval_page(tasks, year, month, user=None, activities=None, categories=None, sel_category='', sel_leader='', sel_assignees=None):
    from config import LEADER_EVAL_NUM_FIELD, LEADER_EVAL_TEXT_FIELD, USERS, display_name
    import json
    sel_assignees = sel_assignees or []

    rows = []
    unique_statuses = set()
    unique_assignees = {}
    for issue in tasks:
        f = issue.get('fields', {})
        st = (f.get('status') or {}).get('name') or ''
        if st:
            unique_statuses.add(st)
        asg_user = i_assignee(issue)
        asg_name = i_assignee_name(issue)
        unique_assignees[asg_user] = asg_name
        num_val = f.get(LEADER_EVAL_NUM_FIELD)
        num_str = str(num_val) if num_val is not None else ''
        text_val = f.get(LEADER_EVAL_TEXT_FIELD) or ''
        # "Đã đánh giá" = 1 trong 2 field Leader đánh giá có value
        evaluated = '1' if (num_val is not None or text_val.strip()) else '0'

        rows.append(f"""
        <tr class="eval-row" data-status="{esc(st)}" data-key="{esc(issue['key'])}" data-assignee="{esc(asg_user)}" data-evaluated="{evaluated}">
            <td style="text-align:center"><input type="checkbox" class="eval-chk" value="{esc(issue['key'])}"></td>
            <td>{issue_link(issue)}</td>
            <td class="summary-cell clickable" title="{esc(i_summary(issue))}">{esc(i_summary(issue))}</td>
            <td>{esc(asg_name)}</td>
            <td><span class="status {status_class(st)}">{esc(st)}</span></td>
            <td>{esc(num_str)}</td>
            <td><div style="max-height:60px;overflow-y:auto;font-size:0.9em">{esc(text_val)}</div></td>
        </tr>""")

    status_opts = ''
    for st in sorted(unique_statuses):
        status_opts += f'<option value="{esc(st)}">{esc(st)}</option>'

    asg_opts = ''
    for u, n in sorted(unique_assignees.items(), key=lambda kv: kv[1].lower()):
        asg_opts += f'<option value="{esc(u)}">{esc(n)}</option>'

    table_html = f"""
    <div class="card">
    <table class="data-table">
        <thead>
            <tr>
                <th style="width:40px;text-align:center"><input type="checkbox" id="evalCheckAll"></th>
                <th>Key</th>
                <th>Summary</th>
                <th>Assignee</th>
                <th>Status</th>
                <th>Điểm (Số)</th>
                <th>Đánh giá (Text)</th>
            </tr>
        </thead>
        <tbody id="evalTbody">
            {''.join(rows) if rows else '<tr><td colspan="7" class="empty">Không có task nào.</td></tr>'}
        </tbody>
    </table>
    </div>
    """

    cat_opts = '<option value="">-- Tất cả --</option>'
    for c in (categories or []):
        n = c.get('name', '')
        sel = ' selected' if n == sel_category else ''
        cat_opts += f'<option value="{esc(n)}"{sel}>{esc(n)}</option>'

    all_leaders = set(USERS)
    all_leaders.add('thanhht1')
    ld_opts = '<option value="">-- Tất cả --</option>'
    for u in sorted(all_leaders):
        sel = ' selected' if u == sel_leader else ''
        ld_opts += f'<option value="{esc(u)}"{sel}>{esc(display_name(u))}</option>'

    excl_hidden = ''.join(f'<input type="hidden" name="assignee" value="{esc(u)}">' for u in sel_assignees)

    excl_dropdown_opts = '<option value="">+ Chọn Assignee...</option>'
    for u in USERS:
        if u not in sel_assignees:
            excl_dropdown_opts += f'<option value="{esc(u)}">{esc(display_name(u))}</option>'

    month_str = f"{year}-{month:02d}"

    chip_css = """
    <style>
    .eval-filter { display:flex; flex-wrap:wrap; gap:14px 16px; align-items:flex-end; }
    .ef { display:flex; flex-direction:column; gap:6px; }
    .eval-flabel { font-size:12px; font-weight:600; color:var(--on-surface-variant); }
    .eval-filter .set-input { height:42px; box-sizing:border-box; margin:0; }
    .ef-month  .set-input { width:140px; }
    .ef-cat    .set-input { width:200px; }
    .ef-leader .set-input { width:150px; }
    .ef-assignee .set-input { width:200px; }
    .eval-filter .btn-primary { height:42px; padding:0 24px; }
    .eval-chips { flex-basis:100%; display:flex; flex-wrap:wrap; gap:8px; margin-top:2px; }
    .eval-chips:empty { display:none; }
    .eval-chip { display:inline-flex; align-items:center; gap:6px; background:var(--surface-container);
        color:var(--on-surface); padding:4px 8px 4px 12px; border-radius:14px; font-size:13px; font-weight:600; }
    .eval-chip-x { cursor:pointer; color:var(--on-surface-variant); font-size:16px; line-height:1;
        width:18px; height:18px; display:inline-flex; align-items:center; justify-content:center; border-radius:50%; }
    .eval-chip-x:hover { color:#fff; background:#f15b50; }
    .eval-row { cursor:pointer; }
    .eval-row:hover { background:var(--surface-low); }
    .eval-row .summary-cell.clickable { color:var(--on-surface); }
    </style>
    """

    name_map_json = json.dumps({u: display_name(u) for u in USERS})
    excl_chips = ''.join(
        f'<span class="eval-chip" data-val="{esc(u)}">{esc(display_name(u))}'
        f'<span class="eval-chip-x" onclick="removeExcl(\'{esc(u)}\')">\u00d7</span></span>'
        for u in sel_assignees)

    # Build JS as a separate string (NOT inside f-string) to avoid {{/}} hell
    js_block = """
    <script>
    (function() {
        function updateCount() {
            var sel = document.querySelectorAll('.eval-chk:checked').length;
            var lbl = document.getElementById('evalSelectedCount');
            if (lbl) lbl.textContent = sel + ' task \\u0111ang ch\\u1ecdn';
        }

        /* Status + Assignee filters (combined) */
        var sf = document.getElementById('statusFilter');
        var af = document.getElementById('asgFilter');
        var ef = document.getElementById('evalStateFilter');
        function applyRowFilters() {
            var sv = sf ? sf.value : '';
            var av = af ? af.value : '';
            var ev = ef ? ef.value : '';
            document.querySelectorAll('.eval-row').forEach(function(r) {
                var ok = (!sv || r.getAttribute('data-status') === sv) &&
                         (!av || r.getAttribute('data-assignee') === av) &&
                         (!ev || r.getAttribute('data-evaluated') === ev);
                if (ok) {
                    r.style.display = '';
                } else {
                    r.style.display = 'none';
                    var c = r.querySelector('.eval-chk');
                    if (c) c.checked = false;
                }
            });
            updateCount();
        }
        if (sf) sf.addEventListener('change', applyRowFilters);
        if (af) af.addEventListener('change', applyRowFilters);
        if (ef) ef.addEventListener('change', applyRowFilters);

        /* Check-all */
        var ca = document.getElementById('evalCheckAll');
        if (ca) ca.addEventListener('change', function() {
            var me = this;
            document.querySelectorAll('.eval-chk').forEach(function(c) {
                var row = c.closest('tr');
                if (row && row.style.display !== 'none') c.checked = me.checked;
            });
            updateCount();
        });

        /* Individual checkboxes */
        document.querySelectorAll('.eval-chk').forEach(function(c) {
            c.addEventListener('change', updateCount);
        });

        /* Click a row -> open detail drawer (ignore checkbox + links) */
        var tbody = document.getElementById('evalTbody');
        if (tbody) tbody.addEventListener('click', function(e) {
            if (e.target.closest('input, a, label, button')) return;
            var row = e.target.closest('tr.eval-row');
            if (!row) return;
            var key = row.getAttribute('data-key');
            if (key && window.__openDetail) window.__openDetail(key);
        });

        /* Batch eval */
        window._doBatchEval = async function() {
            var keys = Array.from(document.querySelectorAll('.eval-chk:checked')).map(function(c){ return c.value; });
            if (keys.length === 0) { alert('Vui l\\u00f2ng ch\\u1ecdn \\u00edt nh\\u1ea5t 1 task.'); return; }
            var num_val = document.getElementById('evalNum').value;
            var text_val = document.getElementById('evalText').value;
            if (!num_val && !text_val) { alert('Vui l\\u00f2ng nh\\u1eadp \\u0111i\\u1ec3m ho\\u1eb7c text.'); return; }

            var resDiv = document.getElementById('evalResult');
            var btn = document.getElementById('btnBatchEval');
            resDiv.textContent = '\\u0110ang x\\u1eed l\\u00fd...';
            resDiv.style.color = '#a5adba';
            btn.disabled = true;

            try {
                var r = await fetch('/batch-eval', {
                    method: 'POST',
                    headers: {'Content-Type': 'application/json'},
                    body: JSON.stringify({keys: keys, num_val: num_val || null, text_val: text_val || null})
                });
                var data = await r.json();
                resDiv.textContent = data.msg || (data.ok ? 'Th\\u00e0nh c\\u00f4ng' : 'L\\u1ed7i');
                resDiv.style.color = data.ok ? '#94C748' : '#F87168';
                if (data.ok) setTimeout(function(){ location.reload(); }, 2000);
            } catch (e) {
                resDiv.textContent = 'L\\u1ed7i m\\u1ea1ng: ' + e;
                resDiv.style.color = '#F87168';
            } finally {
                btn.disabled = false;
            }
        };

        /* Assignee multi-select: dropdown adds a chip on its own row below */
        var dd = document.getElementById('exclDropdown');
        var chips = document.getElementById('exclChipsContainer');
        var hidden = document.getElementById('exclHiddenInputs');

        window.removeExcl = function(val) {
            var chip = chips.querySelector('.eval-chip[data-val="' + val + '"]');
            if (chip) chip.remove();
            var inp = hidden.querySelector('input[value="' + val + '"]');
            if (inp) inp.remove();
            var opt = document.createElement('option');
            opt.value = val;
            opt.textContent = (window.EVAL_NAMES && window.EVAL_NAMES[val]) || val;
            dd.appendChild(opt);
        };

        function addExcl(val) {
            var name = (window.EVAL_NAMES && window.EVAL_NAMES[val]) || val;
            var chip = document.createElement('span');
            chip.className = 'eval-chip';
            chip.setAttribute('data-val', val);
            chip.textContent = name;
            var x = document.createElement('span');
            x.className = 'eval-chip-x';
            x.textContent = '\\u00d7';
            x.onclick = function() { removeExcl(val); };
            chip.appendChild(x);
            chips.appendChild(chip);
            var inp = document.createElement('input');
            inp.type = 'hidden';
            inp.name = 'assignee';
            inp.value = val;
            hidden.appendChild(inp);
        }

        if (dd) dd.addEventListener('change', function() {
            var val = this.value;
            if (!val) return;
            var opt = this.options[this.selectedIndex];
            if (opt) opt.remove();
            this.value = '';
            addExcl(val);
        });
    })();
    </script>
    """
    js_block = '<script>window.EVAL_NAMES = ' + name_map_json + ';</script>' + js_block

    inner = f"""
    {chip_css}
    <div class="page-head">
        <div>
            <h2 class="page-title">\u2b50 \u0110\u00e1nh gi\u00e1 Task QA (Leader)</h2>
            <div class="page-sub">L\u1ecdc task, ch\u1ecdn nhi\u1ec1u task \u0111\u1ec3 ch\u1ea5m \u0111i\u1ec3m v\u00e0 \u0111\u00e1nh gi\u00e1 h\u00e0ng lo\u1ea1t. L\u01b0u tr\u1ef1c ti\u1ebfp l\u00ean Jira.</div>
        </div>
    </div>

    <!-- B\u1ed9 l\u1ecdc -->
    <div class="card" style="margin-bottom:20px; padding:16px;">
        <form action="/leader-eval" method="GET" id="evalFilterForm" class="eval-filter">
            <div class="ef ef-month">
                <label class="eval-flabel">Th\u00e1ng:</label>
                <input type="month" name="month" value="{month_str}" class="set-input">
            </div>
            <div class="ef ef-cat">
                <label class="eval-flabel">Category:</label>
                <select name="category" class="set-input">{cat_opts}</select>
            </div>
            <div class="ef ef-leader">
                <label class="eval-flabel">Leader:</label>
                <select name="leader" class="set-input">{ld_opts}</select>
            </div>
            <div class="ef ef-assignee">
                <label class="eval-flabel">Assignee:</label>
                <select id="exclDropdown" class="set-input">{excl_dropdown_opts}</select>
            </div>
            <button type="submit" class="btn btn-primary">L\u1ecdc</button>
            <div id="exclHiddenInputs" style="display:none;">{excl_hidden}</div>
            <div class="eval-chips" id="exclChipsContainer">{excl_chips}</div>
        </form>
    </div>

    <div style="display:flex; gap:20px; align-items:flex-start;">
        <div style="flex:1;">
            <div class="section">
                <div style="display:flex; justify-content:space-between; align-items:center; margin-bottom:12px;">
                    <div style="display:flex; align-items:center; gap:16px;">
                        <h3 style="margin:0;">Danh s\u00e1ch Task ({len(tasks)})</h3>
                        <div style="display:flex; align-items:center; gap:8px;">
                            <label style="font-size:13px; font-weight:600; color:var(--on-surface-variant);">L\u1ecdc Status:</label>
                            <select id="statusFilter" class="set-input" style="margin:0; padding:4px 28px 4px 8px; font-size:13px; width:160px;">
                                <option value="">-- T\u1ea5t c\u1ea3 --</option>
                                {status_opts}
                            </select>
                        </div>
                        <div style="display:flex; align-items:center; gap:8px;">
                            <label style="font-size:13px; font-weight:600; color:var(--on-surface-variant);">L\u1ecdc Assignee:</label>
                            <select id="asgFilter" class="set-input" style="margin:0; padding:4px 28px 4px 8px; font-size:13px; width:160px;">
                                <option value="">-- T\u1ea5t c\u1ea3 --</option>
                                {asg_opts}
                            </select>
                        </div>
                        <div style="display:flex; align-items:center; gap:8px;">
                            <label style="font-size:13px; font-weight:600; color:var(--on-surface-variant);">\u0110\u00e1nh gi\u00e1:</label>
                            <select id="evalStateFilter" class="set-input" style="margin:0; padding:4px 28px 4px 8px; font-size:13px; width:160px;">
                                <option value="">-- T\u1ea5t c\u1ea3 --</option>
                                <option value="1">\u0110\u00e3 \u0111\u00e1nh gi\u00e1</option>
                                <option value="0">Ch\u01b0a \u0111\u00e1nh gi\u00e1</option>
                            </select>
                        </div>
                    </div>
                    <span id="evalSelectedCount" style="color:#85b8ff; font-weight:bold;">0 task \u0111ang ch\u1ecdn</span>
                </div>
                {table_html}
            </div>
        </div>
        <div style="width:320px; position:sticky; top:20px;">
            <div class="card" style="padding:20px;">
                <h3>C\u1eadp nh\u1eadt h\u00e0ng lo\u1ea1t</h3>
                <p class="set-note" style="margin-top:4px;">Ch\u1ec9 c\u1eadp nh\u1eadt cho c\u00e1c task \u0111ang \u0111\u01b0\u1ee3c ch\u1ecdn (tick) \u1edf b\u00ean tr\u00e1i.</p>
                <div style="display:flex; flex-direction:column; gap:12px; margin-top:16px;">
                    <div>
                        <label style="display:block; margin-bottom:4px; font-weight:500;">\u0110i\u1ec3m (S\u1ed1):</label>
                        <input type="number" id="evalNum" class="set-input" placeholder="VD: 8.5" step="0.1">
                        <small style="color:var(--on-surface-variant);">B\u1ecf tr\u1ed1ng n\u1ebfu kh\u00f4ng mu\u1ed1n \u0111\u1ed5i</small>
                    </div>
                    <div>
                        <label style="display:block; margin-bottom:4px; font-weight:500;">\u0110\u00e1nh gi\u00e1 (Text):</label>
                        <textarea id="evalText" class="set-input" rows="4" placeholder="Nh\u1eadn x\u00e9t..."></textarea>
                        <small style="color:var(--on-surface-variant);">B\u1ecf tr\u1ed1ng n\u1ebfu kh\u00f4ng mu\u1ed1n \u0111\u1ed5i</small>
                    </div>
                    <button type="button" class="btn btn-primary" id="btnBatchEval" style="margin-top:8px;" onclick="window._doBatchEval()">L\u01b0u l\u00ean Jira</button>
                    <div id="evalResult" style="margin-top:8px; font-size:0.9em; white-space:pre-wrap;"></div>
                </div>
            </div>
        </div>
    </div>

    {js_block}
    """
    return _document_v2(inner, 'leadereval', user, activities or [], title=f'\u0110\u00e1nh gi\u00e1 th\u00e1ng {month}/{year} \u2014 QA Dashboard')
