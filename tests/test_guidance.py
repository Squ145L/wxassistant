# tests/test_guidance.py
import pytest

from src.utils import account_paths as ap
from src.utils import calibration as cal
from src.utils import coordinates as coord
from src.utils import guidance as g


@pytest.fixture
def tmp_cache(tmp_path, monkeypatch):
    monkeypatch.setattr(ap, "CACHE_DIR", tmp_path)
    return tmp_path


def test_ok_when_all_set(tmp_cache):
    coord.save_coordinates({"tab_chat": (0.5, 0.5), "chat_first": (0.3, 0.3)}, "账户1")
    cal.save_calibration("chat_title", {"LEFT_MARGIN": 0.05}, "账户1")
    assert g.check_ready("账户1", g.SEND_COORD_KEYS, ["chat_title"]) == g.READY_OK


def test_need_coords_first_even_if_calibrated(tmp_cache):
    # 坐标未配置 → 即使 OCR 已校准也先报 need_coords（坐标优先）
    cal.save_calibration("chat_title", {"LEFT_MARGIN": 0.05}, "账户1")
    assert g.check_ready("账户1", g.SEND_COORD_KEYS, ["chat_title"]) == g.READY_NEED_COORDS


def test_need_calib_when_coords_ok(tmp_cache):
    coord.save_coordinates({"tab_chat": (0.5, 0.5), "chat_first": (0.3, 0.3)}, "账户1")
    assert g.check_ready("账户1", g.SEND_COORD_KEYS, ["chat_title"]) == g.READY_NEED_CALIB


def test_need_coords_even_with_partial(tmp_cache):
    # 只配了其中一个坐标 → 仍 need_coords
    coord.save_coordinates({"tab_chat": (0.5, 0.5)}, "账户1")
    assert g.check_ready("账户1", g.SEND_COORD_KEYS, []) == g.READY_NEED_COORDS


def test_scan_needs_its_coord_set(tmp_cache):
    # 扫描需要 cm_search_box 等，未配置 → need_coords
    coord.save_coordinates({"tab_contacts": (0.5, 0.5), "btn_contacts_mgr": (0.3, 0.3),
                            "cm_search_box": (0.0, 0.0), "cm_list_focus": (0.7, 0.3)}, "账户1")
    assert g.check_ready("账户1", g.SCAN_COORD_KEYS, ["contacts_list"]) == g.READY_NEED_COORDS


def test_calib_labels_have_friendly_names():
    assert g.CALIB_LABELS["chat_title"] == "聊天标题"
    assert g.CALIB_LABELS["contacts_list"] == "通讯录区域"
