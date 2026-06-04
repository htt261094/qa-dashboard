"""Person-in-charge (PIC) per project line: seed defaults + load/save to .pic_config.json."""
import json

from config import PIC_FILE

PIC_PEOPLE = ['ThoLT', 'ThanhHT', 'PhuongCT', 'QuangBM', 'NhungNH']

PIC_DEFAULT = [
    {'group': 'Core', 'rows': [
        {'flow': 'Chi Hộ - Luồng chính', 'pic': 'ThoLT'},
        {'flow': 'Thu Hộ', 'pic': 'ThanhHT'},
        {'flow': 'Cổng Thanh Toán (CTT) - Luồng chính', 'pic': 'PhuongCT'},
        {'flow': 'Retail - Luồng chính', 'pic': 'QuangBM'},
        {'flow': 'Ví Điện Tử (VĐT)', 'pic': 'PhuongCT'},
        {'flow': 'Bill Payment', 'pic': 'PhuongCT'},
        {'flow': 'ERP - Luồng Onboarding / Hợp đồng MRC', 'pic': 'ThoLT'},
        {'flow': 'ICCP (Đầu vào VPBank)', 'pic': 'NhungNH'},
        {'flow': 'VietQRPay', 'pic': 'NhungNH'},
    ]},
    {'group': 'QTRR', 'rows': [
        {'flow': 'Luồng quyết toán', 'pic': 'PhuongCT'},
        {'flow': 'Đối soát nội bộ', 'pic': 'ThanhHT'},
        {'flow': 'Blacklist', 'pic': 'ThanhHT'},
        {'flow': 'Whitelist', 'pic': 'ThanhHT'},
    ]},
    {'group': 'B2B', 'rows': [
        {'flow': 'Luồng giao dịch VA, Thẻ tín dụng, Trả góp, autodebit, UCOF (thanh toán bằng token), ICCP (Đầu ra Bizzi)', 'pic': 'ThoLT'},
        {'flow': 'VietQRPay', 'pic': 'ThanhHT'},
        {'flow': 'Admin Leadgen', 'pic': 'NhungNH'},
        {'flow': 'Tra soát', 'pic': 'QuangBM'},
        {'flow': 'Đối soát, quyết toán', 'pic': 'ThoLT'},
        {'flow': 'Đối chiếu số dư', 'pic': 'ThoLT'},
    ]},
    {'group': 'CB', 'rows': [
        {'flow': '', 'pic': 'ThoLT'},
    ]},
    {'group': 'HRM', 'rows': [
        {'flow': '', 'pic': 'QuangBM'},
    ]},
]


def load_pic():
    if PIC_FILE.exists():
        try:
            data = json.loads(PIC_FILE.read_text(encoding='utf-8'))
            if isinstance(data, list) and data:
                return data
        except (json.JSONDecodeError, OSError):
            pass
    return PIC_DEFAULT


def save_pic(data):
    try:
        PIC_FILE.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding='utf-8')
        return True
    except OSError:
        return False
