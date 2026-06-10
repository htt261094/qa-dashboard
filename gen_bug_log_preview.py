#!/usr/bin/env python3
"""Preview TĨNH tab Bug Log (#55) — render bằng HÀM THẬT `render_bug_log_v2`.

Khác bản preview đầu (hand-built): nay gọi thẳng render.render_bug_log_v2 với data seed
(đúng shape bug_log_store.load_bug_log) + links seed (task_link.load_links) → output =
HTML production. Chèn mock fetch cho /search-parents, /link-task, /sync-bug-log để bấm
thử OFFLINE (tab tháng, tick test case, liên kết task, gỡ link, pager) mà không cần Jira.

KHÔNG sửa app code. Chạy:  python gen_bug_log_preview.py  →  mở preview_bug_log.html
"""
import json
import os

os.environ.setdefault('JIRA_URL', 'https://jira.baokim.vn:8443')
os.environ.setdefault('JIRA_PAT', 'preview-fake')

from render import render_bug_log_v2  # noqa: E402


def _bug(project, month, no, feature, summary, severity, status, qa, created, dev=''):
    return {'project': project, 'bug_no': no, 'month': month, 'feature': feature,
            'summary': summary, 'severity': severity, 'status': status,
            'qa_pic': qa, 'dev_pic': dev, 'created': created}


def fake_data():
    def k(p, m, n):
        return f"{p}#{m}#{n}"
    bugs6 = {
        k('DA6', '2026-06', '23'): _bug('DA6', '2026-06', '23', 'Checkout', 'Lỗi crash khi thanh toán bằng VNPay', 'Nghiêm trọng', 'New', 'Nhung', '2026-06-08', dev='Hùng'),
        k('DA6', '2026-06', '08'): _bug('DA6', '2026-06', '08', 'Profile', 'Icon hiển thị sai ở trang Profile', 'Thấp', 'Fixed', 'Thơ', '2026-06-07', dev='Hùng'),
        k('DA6', '2026-06', '24'): _bug('DA6', '2026-06', '24', 'Wallet', 'Số dư ví không refresh sau khi nạp', 'Cao', 'Fixing', 'Nhung', '2026-06-06', dev='Sơn'),
        k('DA6', '2026-06', '25'): _bug('DA6', '2026-06', '25', 'Auth', 'Validation form đăng ký', 'Trung bình', 'Reopen', 'Quang', '2026-06-05', dev='Sơn'),
    }
    bugs5 = {
        k('DA6', '2026-05', '11'): _bug('DA6', '2026-05', '11', 'Đối soát', 'File đối soát thiếu cột phí', 'Trung bình', 'Closed', 'Phương', '2026-05-20', dev='Hùng'),
        k('DA6', '2026-05', '12'): _bug('DA6', '2026-05', '12', 'ICCP', 'Sai mã phản hồi khi timeout', 'Cao', 'Rejected', 'Quang', '2026-05-18', dev='Sơn'),
    }
    bugs = {}
    bugs.update(bugs6)
    bugs.update(bugs5)
    return {
        'files': {'1x7v9kL0': {'name': 'QA_Reporting_Master_File_2024.xlsx',
                               'project': 'DA6', 'count': len(bugs), 'bugs': bugs}},
        # reopen tích luỹ mock (issue #69): Sơn fix ẩu — bug #25 bật 2 lần (fix 3 lần), #24 bật 1 (fix 2)
        'reopen': {
            k('DA6', '2026-06', '25'): {'count': 2, 'fix': 3, 'dev': 'Sơn', 'project': 'DA6', 'month': '2026-06', 'last': '2026-06-09T10:00:00'},
            k('DA6', '2026-06', '24'): {'count': 1, 'fix': 2, 'dev': 'Sơn', 'project': 'DA6', 'month': '2026-06', 'last': '2026-06-08T10:00:00'},
            k('DA6', '2026-06', '08'): {'count': 1, 'fix': 2, 'dev': 'Hùng', 'project': 'DA6', 'month': '2026-06', 'last': '2026-06-07T10:00:00'},
        },
        'synced_at': '2026-06-09T21:30:00',
    }


def fake_links():
    return {'DA6#2026-06#08': {'tasks': ['DA61H26-8812', 'PSIT1H26-2717'], 'by': 'tholt', 'at': '2026-06-09'}}


# mock fetch: /search-parents trả task giả; /link-task echo lại; /sync-bug-log ok; còn lại ok
_MOCK = """<script>(function(){
  window.fetch=function(url,opts){
    var data={ok:true};
    if(url.indexOf('/search-parents')>=0){
      data={ok:true,results:[
        {key:'DA61H26-9011',summary:'[DEV] API ví điện tử',project:'DA6'},
        {key:'DA61H26-9015',summary:'[DEV] Cổng thanh toán VNPay',project:'DA6'},
        {key:'PSIT1H26-2717',summary:'[DEV] Đăng ký tài khoản',project:'PSIT1'}]};
    } else if(url.indexOf('/link-task')>=0){
      var b=JSON.parse(opts.body||'{}'),m={};
      window.__plinks=window.__plinks||{'DA6#2026-06#08':['DA61H26-8812']};
      (b.keys||[]).forEach(function(k){
        var cur=(window.__plinks[k]||[]).slice();
        if(b.op==='remove') cur=cur.filter(function(t){return t!==b.task;});
        else if(b.op==='clear') cur=[];
        else if(b.task && cur.indexOf(b.task)<0) cur.push(b.task);
        window.__plinks[k]=cur; m[k]=cur;
      });
      data={ok:true,links:m};
    } else if(url.indexOf('/sync-bug-log')>=0){ data={ok:true,synced_at:'now',count:6,changed:0}; }
    else if(url.indexOf('/activity-feed')>=0){ data={ok:true,activities:[],tasks:{}}; }
    return Promise.resolve({ok:true,status:200,json:function(){return Promise.resolve(data);}});
  };
})();</script>"""
_BANNER = ('<div style="position:fixed;bottom:10px;left:10px;z-index:99999;background:#172b4d;color:#fff;'
           'padding:6px 12px;border-radius:6px;font:600 12px sans-serif;opacity:.9">'
           '🔍 PREVIEW Bug Log (#55) — render THẬT + data giả, mọi nút mock</div>')


def main():
    html = render_bug_log_v2(fake_data(), fake_links(), editable=True,
                             user=('thanhht1@baokim.vn', True), activities=[])
    html = html.replace('href="/settings"', 'href="#"')
    for h in ('href="/logout"', 'href="/roadmap"', 'href="/docs"', 'href="/"', 'href="/my-work"'):
        html = html.replace(h, 'href="#"')
    html = html.replace('<body>', '<body>' + _MOCK, 1)
    html = html.replace('</body>', _BANNER + '</body>', 1)
    with open('preview_bug_log.html', 'w', encoding='utf-8') as f:
        f.write(html)
    print('Đã tạo: preview_bug_log.html (render thật render_bug_log_v2).')


if __name__ == '__main__':
    main()
