from __future__ import annotations

PRACTICE_CONFIRMATION = "Q3_PRACTICE_ONLY"


def require_practice_confirmation(value: str | None) -> None:
    if value == PRACTICE_CONFIRMATION:
        return
    raise RuntimeError(
        "安全停止：本程序只允许连接官方“问题3演练测试/模拟测试”。"
        f"运行前请确认模拟器当前不是正式测试，并添加参数 --confirm-practice {PRACTICE_CONFIRMATION}。"
    )

