from __future__ import annotations

from dataclasses import dataclass

from coding_pet.gui.session_panel import PanelAction


@dataclass(slots=True)
class ReplyBoxModel:
    session_id: str

    def build_request(self, text: str, *, press_enter: bool = True) -> dict[str, object]:
        return {
            "type": "action_request",
            "session_id": self.session_id,
            "action": (
                PanelAction.SEND_REPLY.value
                if press_enter
                else PanelAction.SEND_WITHOUT_ENTER.value
            ),
            "reply_text": text,
            "press_enter": press_enter,
        }
