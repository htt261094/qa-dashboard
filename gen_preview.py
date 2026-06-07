#!/usr/bin/env python3
"""Sinh trang preview TĨNH để check UI mà KHÔNG cần Jira/server.

Dùng render thật (CSS/JS/layout y hệt production) + chèn mock `fetch` để mọi nút
(🔄 transition, 💬 comment, nhãn nội bộ, lưu PAT) bấm được offline — trả JSON giả.

Chạy:  python gen_preview.py   →  mở preview.html trong browser.
Sửa CSS/JS xong chạy lại để cập nhật.
"""
import os
from datetime import datetime, timedelta

os.environ.setdefault('JIRA_URL', 'https://jira.baokim.vn:8443')
os.environ.setdefault('JIRA_PAT', 'preview-fake')

from render import render_page, render_settings_page, render_403  # noqa: E402

_NOW = datetime.now()


def _iso(dt):
    return dt.strftime('%Y-%m-%dT%H:%M:%S.000+0700')


def mk(key, status, summary, assignee='quangbm', reporter='hiennt19',
       due=None, updated_days=0, itype='Sub-task', prio='Medium'):
    return {'key': key, 'fields': {
        'summary': summary,
        'status': {'name': status},
        'assignee': {'name': assignee, 'displayName': assignee},
        'reporter': {'name': reporter, 'displayName': reporter},
        'duedate': due,
        'created': _iso(_NOW - timedelta(days=2)),
        'updated': _iso(_NOW - timedelta(days=updated_days)),
        'resolutiondate': _iso(_NOW - timedelta(hours=5)) if status == 'DONE' else None,
        'issuetype': {'name': itype},
        'priority': {'name': prio},
        'comment': {'comments': []},
    }}


def fake_data():
    d = lambda days: (_NOW + timedelta(days=days)).strftime('%Y-%m-%d')  # noqa: E731
    active = [
        mk('DA51H26-101', 'In Progress', '[QA] Test luồng Chi Hộ - happy case', 'quangbm', due=d(-3), updated_days=0, prio='High'),
        mk('DA51H26-102', 'TO DO', '[QA] Viết test case Cổng Thanh Toán', 'quangbm', due=d(-1)),
        mk('DA61H26-210', 'PENDING', '[QA] Regression Ví Điện Tử', 'quangbm', due=d(2), updated_days=7, prio='High'),
        mk('PSIT1H26-55', 'In Progress', '[QA] Kiểm thử API ICCP đầu vào VPBank', 'quangbm', due=d(1), updated_days=6),
        mk('DA2B-9', 'TO DO', '[QA] Test Admin Leadgen B2B', 'quangbm', due=d(5)),
        mk('DA51H26-115', 'TO DO', '[QA] Đối soát nội bộ - case lỗi', 'quangbm', due=None),
    ]
    new24 = [mk('DA51H26-130', 'TO DO', '[QA] Bug retest sau deploy hotfix', 'quangbm', 'quangbm', due=d(3))]
    done_week = [
        mk('DA61H26-200', 'DONE', '[QA] Hoàn tất test VietQRPay', 'quangbm'),
        mk('PSIT1H26-40', 'DONE', '[QA] Test Bill Payment - pass', 'quangbm'),
    ]
    return {'active': active, 'new24': new24, 'done_week': done_week,
            'created_week': 4, 'resolved_week': 2, 'fetched_at': _NOW}


def fake_activities():
    return [
        {'id': 'DA51H26-101#cstat#1', 'kind': 'custom_status', 'key': 'DA51H26-101',
         'summary': '[QA] Test luồng Chi Hộ - happy case', 'author': 'Quang',
         'when': _iso(_NOW - timedelta(hours=1)), 'new': 'Dev đang fix bug'},
        {'id': 'DA61H26-210#st', 'kind': 'status', 'key': 'DA61H26-210',
         'summary': '[QA] Regression Ví Điện Tử', 'author': 'Quang',
         'when': _iso(_NOW - timedelta(hours=3)), 'old': 'TO DO', 'new': 'PENDING'},
        {'id': 'PSIT1H26-55#cmt#9', 'kind': 'comment', 'key': 'PSIT1H26-55',
         'summary': '[QA] Kiểm thử API ICCP đầu vào VPBank', 'author': 'Hiền',
         'when': _iso(_NOW - timedelta(hours=6)), 'body': 'Đã confirm requirement với BA, QA tiếp tục test nhé.'},
    ]


# mock fetch: mọi endpoint POST trả JSON giả -> UI bấm được offline
def _mock(has_pat):
    """Mock fetch. has_pat=True: trả transition động (chỉ status đổi được) + thao tác ok.
    has_pat=False: /jira-transitions + /add-comment trả no_pat; custom status VẪN ok."""
    if has_pat:
        jira = ("data = {ok:true, transitions:["
                "{id:'21',to:'In Progress'},{id:'31',to:'PENDING'},"
                "{id:'41',to:'DONE'},{id:'51',to:'CANCELLED'}]};")
        comment = "data = {ok:true, msg:'Đã gửi comment lên Jira. (PREVIEW)'};"
    else:
        jira = "data = {ok:false, code:'no_pat', msg:'Bạn chưa cung cấp PAT. Vào ⚙ Cài đặt để thêm. (PREVIEW)'};"
        comment = "data = {ok:false, code:'no_pat', msg:'Bạn chưa cung cấp PAT. Vào ⚙ Cài đặt để thêm. (PREVIEW)'};"
    return ("<script>(function(){window.fetch=function(url,opts){var data={ok:true};"
            f"if(url.indexOf('/jira-transitions')>=0){{{jira}}}"
            "else if(url.indexOf('/do-transition')>=0)data={ok:true,msg:'Đã đổi status trên Jira. (PREVIEW)'};"
            f"else if(url.indexOf('/add-comment')>=0){{{comment}}}"
            "else if(url.indexOf('/set-custom-status')>=0)data={ok:true};"
            "else if(url.indexOf('/save-pat')>=0)data={ok:true,msg:'Đã lưu PAT (PREVIEW).'};"
            "else if(url.indexOf('/delete-pat')>=0)data={ok:true};"
            "return Promise.resolve({json:function(){return Promise.resolve(data);},ok:true,status:200});};})();</script>")

_BANNER = ('<div style="position:fixed;bottom:10px;left:10px;z-index:99999;background:#172b4d;color:#fff;'
           'padding:6px 12px;border-radius:6px;font:600 12px sans-serif;opacity:.85">'
           '🔍 PREVIEW MODE — data giả, mọi nút trả kết quả giả lập (không gọi Jira)</div>')


def _patch(html, home_file, has_pat=True, extra=''):
    html = html.replace('<body>', '<body>' + _mock(has_pat), 1)
    html = html.replace('</body>', _BANNER + extra + '</body>', 1)
    html = html.replace('href="/settings"', 'href="preview_settings.html"')
    html = html.replace('href="/"', f'href="{home_file}"')
    for h in ('href="/report"', 'href="/roadmap"', 'href="/docs"', 'href="/logout"'):
        html = html.replace(h, 'href="#"')
    return html


def _hint(text):
    return ('<div style="position:fixed;bottom:44px;left:10px;z-index:99999;background:#7c4dff;color:#fff;'
            f'padding:6px 12px;border-radius:6px;font:600 12px sans-serif;max-width:340px">{text}</div>')


def main():
    data = fake_data()
    acts = fake_activities()
    overlay = {'DA51H26-101': {'v': 'dev_fixing', 'by': 'quangbm', 'at': _iso(_NOW)},
               'DA61H26-210': {'v': 'wait_deploy', 'by': 'quangbm', 'at': _iso(_NOW)}}

    def page(is_admin, email):
        return render_page(data, {'DA51H26-130'}, False, acts, 7, roadmap_data=[],
                           user=(email, is_admin), custom_overlay=overlay)

    admin = page(True, 'thanhht1@baokim.vn')
    personal = page(False, 'quangbm@baokim.vn')
    settings = render_settings_page(True, user=('quangbm@baokim.vn', False))

    hp = _hint('CÓ PAT: bấm ▾ → nhóm "Status Jira" chỉ hiện các status đổi được (fetch động). '
               'Chọn custom (●) vẫn chỉ đổi dashboard.')
    np = _hint('CHƯA có PAT: bấm ▾ → "Status Jira" hiện 🔒 (bấm ra popup). Comment + Enter → popup. '
               'NHƯNG chọn custom status (●) VẪN đổi được bình thường.')

    files = {
        'preview.html': _patch(admin, 'preview.html', has_pat=True),
        'preview_personal.html': _patch(personal, 'preview_personal.html', has_pat=True, extra=hp),
        'preview_personal_nopat.html': _patch(personal, 'preview_personal_nopat.html', has_pat=False, extra=np),
        'preview_settings.html': _patch(settings, 'preview_personal.html', has_pat=True),
        'preview_403.html': render_403().replace('href="/logout"', 'href="#"'),
    }
    for name, html in files.items():
        with open(name, 'w', encoding='utf-8') as f:
            f.write(html)
    print('Đã tạo: preview.html, preview_personal.html (có PAT), preview_personal_nopat.html (chưa PAT), '
          'preview_settings.html, preview_403.html')


if __name__ == '__main__':
    main()
