from src.utils import account_paths as ap
from src.utils import calibration as cal


def test_load_returns_default_when_no_files(tmp_path, monkeypatch):
    monkeypatch.setattr(ap, "CACHE_DIR", tmp_path)
    monkeypatch.setattr(cal, "OCR_CALIBRATION_PATH", tmp_path / "ocr_calibration.json")
    c = cal.load_calibration("chat_title", "账户1")
    assert c["LEFT_MARGIN"] == cal.DEFAULT_CALIBRATION["chat_title"]["LEFT_MARGIN"]


def test_global_file_applies(tmp_path, monkeypatch):
    monkeypatch.setattr(ap, "CACHE_DIR", tmp_path)
    monkeypatch.setattr(cal, "OCR_CALIBRATION_PATH", tmp_path / "ocr_calibration.json")
    cal.save_calibration("chat_title", {"LEFT_MARGIN": 0.2}, None)
    c = cal.load_calibration("chat_title", "账户1")   # 账户无文件 → 继承全局
    assert c["LEFT_MARGIN"] == 0.2


def test_account_overrides_global(tmp_path, monkeypatch):
    monkeypatch.setattr(ap, "CACHE_DIR", tmp_path)
    monkeypatch.setattr(cal, "OCR_CALIBRATION_PATH", tmp_path / "ocr_calibration.json")
    cal.save_calibration("chat_title", {"LEFT_MARGIN": 0.2}, None)
    cal.save_calibration("chat_title", {"LEFT_MARGIN": 0.9}, "账户1")
    c = cal.load_calibration("chat_title", "账户1")
    assert c["LEFT_MARGIN"] == 0.9
    g = cal.load_calibration("chat_title", None)
    assert g["LEFT_MARGIN"] == 0.2     # 全局不受账户影响


def test_account_without_file_falls_back_to_global(tmp_path, monkeypatch):
    monkeypatch.setattr(ap, "CACHE_DIR", tmp_path)
    monkeypatch.setattr(cal, "OCR_CALIBRATION_PATH", tmp_path / "ocr_calibration.json")
    cal.save_calibration("contacts_list", {"BOTTOM_MARGIN": 0.1}, None)
    c = cal.load_calibration("contacts_list", "账户2")
    assert c["BOTTOM_MARGIN"] == 0.1


def test_calibration_has_key_false_when_missing(tmp_path, monkeypatch):
    monkeypatch.setattr(ap, "CACHE_DIR", tmp_path)
    monkeypatch.setattr(cal, "OCR_CALIBRATION_PATH", tmp_path / "ocr_calibration.json")
    assert not cal.calibration_has_key("chat_title", "账户1")


def test_calibration_has_key_true_via_global(tmp_path, monkeypatch):
    monkeypatch.setattr(ap, "CACHE_DIR", tmp_path)
    monkeypatch.setattr(cal, "OCR_CALIBRATION_PATH", tmp_path / "ocr_calibration.json")
    cal.save_calibration("chat_title", {"LEFT_MARGIN": 0.2}, None)
    assert cal.calibration_has_key("chat_title", "账户1")   # 继承全局也算已校准
    assert cal.calibration_has_key("chat_title", None)


def test_save_isolates_accounts(tmp_path, monkeypatch):
    monkeypatch.setattr(ap, "CACHE_DIR", tmp_path)
    monkeypatch.setattr(cal, "OCR_CALIBRATION_PATH", tmp_path / "ocr_calibration.json")
    cal.save_calibration("chat_title", {"LEFT_MARGIN": 0.5}, "账户A")
    cal.save_calibration("chat_title", {"LEFT_MARGIN": 0.6}, "账户B")
    assert cal.load_calibration("chat_title", "账户A")["LEFT_MARGIN"] == 0.5
    assert cal.load_calibration("chat_title", "账户B")["LEFT_MARGIN"] == 0.6


def test_reset_removes_key(tmp_path, monkeypatch):
    monkeypatch.setattr(ap, "CACHE_DIR", tmp_path)
    monkeypatch.setattr(cal, "OCR_CALIBRATION_PATH", tmp_path / "ocr_calibration.json")
    cal.save_calibration("chat_title", {"LEFT_MARGIN": 0.5}, "账户1")
    cal.reset_calibration("chat_title", "账户1")
    assert not cal.calibration_has_key("chat_title", "账户1")
