# tests/test_smoke.py
def test_project_importable():
    """能 import 纯 Python 服务模块"""
    from src.services.send_service import SendService
    from src.services.template_engine import TemplateEngine
    assert SendService is not None
    assert TemplateEngine is not None
