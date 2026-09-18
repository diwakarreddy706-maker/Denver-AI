"""Deterministic Tier-1 Intent Router for Denver AI Assistant."""

from __future__ import annotations

import re
from typing import Any

from denver.automation.registry import AutomationRegistry
from denver.commands.models import (
    CommandCategory,
    CommandIntent,
    CommandRiskLevel,
)
from denver.logging.logger import get_logger

logger = get_logger("router")


class IntentRouter:
    """Classifies normalized text commands into strongly-typed action intents without LLM overhead."""

    def __init__(self, registry: AutomationRegistry | None = None) -> None:
        self._registry = registry or AutomationRegistry()
        self._build_rules()

    def _build_rules(self) -> None:
        # Precompile high-frequency intent regex patterns
        # 1. Utility
        self._time_re = re.compile(r"^(?:what(?:'s|\s+is)?(?:\s+the)?\s+time(?:\s+is\s+it)?|current\s+time|tell\s+me\s+the\s+time|time)$")
        self._date_re = re.compile(r"^(?:what(?:'s|\s+is)?(?:\s+the|\s+today's)?\s+date(?:\s+is\s+it)?|current\s+date|today(?:'s)?\s+date|date\s+today|date)$")

        # 2. System Telemetry
        self._sys_status_re = re.compile(r"^(?:system\s+status|system\s+health|status\s+report|system\s+info|how\s+are\s+you)$")
        self._cpu_re = re.compile(r"^(?:(?:what(?:'s|\s+is)?(?:\s+the|\s+my)?\s+)?cpu(?:\s+usage|\s+percent|\s+load|\s+telemetry)?|get\s+cpu)$")
        self._ram_re = re.compile(r"^(?:(?:what(?:'s|\s+is)?(?:\s+the|\s+my)?\s+)?(?:ram|memory)(?:\s+usage|\s+percent|\s+load|\s+telemetry)?|get\s+ram|get\s+memory)$")
        self._battery_re = re.compile(r"^(?:(?:what(?:'s|\s+is)?(?:\s+the|\s+my)?\s+)?battery(?:\s+status|\s+level|\s+percent|\s+percentage)?|get\s+battery)$")

        # 3. Application Launch & Close
        self._app_open_re = re.compile(r"^(?:open|launch|start|run)\s+(.+)$")
        self._app_close_re = re.compile(r"^(?:close|quit|exit|kill|terminate)\s+(.+)$")

        # 4. Notes
        self._note_create_colon_re = re.compile(r"^(?:create\s+note|add\s+note|new\s+note)\s+([^:]+):\s*(.+)$")
        self._note_create_re = re.compile(r"^(?:create\s+note|add\s+note|take\s+a\s+note|save\s+note|note)\s+(?:called\s+([a-zA-Z0-9_\-\s]+)\s+)?(.+)$")
        self._note_list_re = re.compile(r"^(?:list\s+notes|show\s+notes|read\s+notes|get\s+notes|my\s+notes|show\s+my\s+notes)$")
        self._note_search_re = re.compile(r"^(?:search\s+notes\s+(?:for\s+)?|find\s+notes?\s+(?:for\s+)?|lookup\s+notes?\s+)(.+)$")

        # 5. Tasks
        self._task_create_re = re.compile(r"^(?:create\s+task|add\s+task|new\s+task|remind\s+me\s+to|task)\s+(.+)$")
        self._task_list_re = re.compile(r"^(?:list\s+tasks|show\s+tasks|my\s+tasks|get\s+tasks|show\s+my\s+tasks|read\s+tasks)$")
        self._task_complete_re = re.compile(r"^(?:complete\s+task|finish\s+task|done\s+task|mark\s+task\s+(\d+)\s+as\s+done|mark\s+task\s+(\d+)\s+done|complete)\s*(\d+)?$")

        # 6. Preferences
        self._pref_set_fav_re = re.compile(r"^(?:my\s+favorite|my\s+preferred)\s+([a-zA-Z0-9_\-]+)\s+is\s+(.+)\.?$")
        self._pref_set_re = re.compile(r"^(?:set\s+preference|set\s+default)\s+([a-zA-Z0-9_\-]+)\s+to\s+(.+)\.?$")
        self._pref_get_fav_re = re.compile(r"^(?:what(?:'s|\s+is)\s+my\s+(?:favorite|preferred)\s+([a-zA-Z0-9_\-]+)|get\s+preference\s+([a-zA-Z0-9_\-]+))\??$")
        self._pref_list_re = re.compile(r"^(?:list\s+preferences|show\s+preferences|my\s+preferences|show\s+my\s+preferences|show\s+saved\s+preferences)\.?$")

        # 7. Memory Recall & Storage
        self._mem_remember_re = re.compile(r"^(?:remember\s+that|remember|save\s+memory|store\s+memory)\s+(.+)$", re.IGNORECASE)
        self._mem_recall_re = re.compile(
            r"^(?:what\s+(?:do\s+you\s+remember|do\s+you\s+know)\s+about|recall|search\s+memory\s+for|search\s+memory|tell\s+me\s+about)\s+(.+)$",
            re.IGNORECASE,
        )
        self._mem_query_extra_re = re.compile(
            r"^(?:what\s+(?:project|tasks?|notes?|app|routine)?\s*(?:was\s+I|am\s+I)\s+working\s+on|what\s+did\s+I\s+do(?:\s+today)?|what\s+is\s+my\s+current\s+project)$",
            re.IGNORECASE,
        )
        self._mem_export_re = re.compile(r"^(?:export\s+(?:my\s+)?memory(?:\s+data)?|export\s+memories|backup\s+memory)$", re.IGNORECASE)
        self._mem_clear_notes_re = re.compile(r"^(?:clear\s+all\s+(?:my\s+)?notes|delete\s+all\s+(?:my\s+)?notes|clear\s+all\s+memories)$", re.IGNORECASE)
        self._mem_list_re = re.compile(r"^(?:list\s+(?:my\s+)?(?:saved\s+)?memories|show\s+(?:my\s+)?memories|what\s+memories\s+do\s+you\s+have)$", re.IGNORECASE)
        self._mem_forget_re = re.compile(r"^(?:forget|delete\s+memory|remove\s+memory|clear\s+memory)\s+(.+)$", re.IGNORECASE)
        self._clear_context_re = re.compile(r"^(?:clear\s+(?:this\s+)?conversation\s+context|clear\s+context|reset\s+context)\.?$", re.IGNORECASE)


        # 8. Window Management
        self._win_desktop_re = re.compile(r"^(?:show\s+desktop|minimize\s+all(?:\s+windows)?|go\s+to\s+desktop)$")
        self._win_minimize_re = re.compile(r"^(?:minimize\s+window\s+(.+)|minimize\s+(.+))$")
        self._win_maximize_re = re.compile(r"^(?:maximize\s+window\s+(.+)|maximize\s+(.+))$")
        self._win_restore_re = re.compile(r"^(?:restore\s+window\s+(.+)|restore\s+(.+))$")
        self._win_focus_re = re.compile(r"^(?:focus\s+window\s+(.+)|focus\s+(.+)|switch\s+to\s+(.+))$")

        # 9. Volume Control
        self._vol_set_re = re.compile(r"^(?:set\s+volume\s+(?:to\s+)?(\d+)(?:\s*%)?|volume\s+(?:to\s+)?(\d+)(?:\s*%)?)$")
        self._vol_inc_re = re.compile(r"^(?:increase\s+volume|volume\s+up|make\s+it\s+louder|louder)(?:\s+by\s+(\d+)(?:\s*%)?)?$")
        self._vol_dec_re = re.compile(r"^(?:decrease\s+volume|volume\s+down|make\s+it\s+quieter|quieter)(?:\s+by\s+(\d+)(?:\s*%)?)?$")
        self._vol_mute_re = re.compile(r"^(?:mute(?:\s+volume|\s+audio|\s+sound)?|turn\s+sound\s+off)$")
        self._vol_unmute_re = re.compile(r"^(?:unmute(?:\s+volume|\s+audio|\s+sound)?|turn\s+sound\s+on)$")
        self._vol_get_re = re.compile(r"^(?:what(?:'s|\s+is)?(?:\s+the)?\s+volume|get\s+volume|current\s+volume)$")

        # 10. Screenshot
        self._screenshot_re = re.compile(r"^(?:take\s+a?\s*screenshot|capture\s+(?:the\s+)?screen|save\s+a?\s*screenshot|screenshot)$")

        # 11. Browser & Web Navigation
        self._browser_open_re = re.compile(r"^(?:open\s+website\s+(.+)|open\s+url\s+(.+)|go\s+to\s+(.+)|browse\s+(.+))$")

        # 12. Privileged System Control & Confirmation
        self._sys_summary_re = re.compile(r"^(?:system\s+summary|hardware\s+info|computer\s+status|pc\s+info)$")
        self._lock_ws_re = re.compile(r"^(?:lock\s+(?:the\s+|my\s+)?(?:computer|pc|workstation|screen|laptop|device)|lock\s+my\s+computer|lock\s+my\s+laptop|lock)$", re.IGNORECASE)
        self._sleep_re = re.compile(r"^(?:go\s+to\s+sleep(?:\s+mode)?|enter\s+sleep(?:\s+mode)?|sleep\s+mode|sleep|take\s+a\s+nap)$", re.IGNORECASE)
        self._wake_re = re.compile(r"^(?:wake\s+up|are\s+you\s+awake|wake)$", re.IGNORECASE)
        self._assistant_call_re = re.compile(r"^(?:(?:hey|hi|hello|ok|okay)?\s*(?:denver|assistant)|are\s+you\s+there|can\s+you\s+hear\s+me|you\s+there|listen\s+to\s+me)$", re.IGNORECASE)
        self._confirm_re = re.compile(r"^(?:yes|proceed|confirm|do\s+it|confirm\s+(cnf_[a-zA-Z0-9]+))$")
        self._cancel_re = re.compile(r"^(?:no|cancel|abort|stop|don't\s+do\s+it)$")

        # 12b. Clipboard & Typing Automation
        self._clipboard_summary_re = re.compile(r"^(?:summarize\s+(?:my\s+|the\s+)?clipboard|summarize\s+copied\s+text|what\s+is\s+(?:this\s+|my\s+)?clipboard\s+about)$", re.IGNORECASE)
        self._clipboard_read_re = re.compile(r"^(?:read\s+(?:my\s+|the\s+)?clipboard|what(?:'s|\s+is)\s+(?:on\s+)?(?:my\s+)?clipboard|what\s+did\s+i\s+copy|read\s+copied\s+text|clipboard)$", re.IGNORECASE)
        self._type_text_re = re.compile(r"^(?:type|write|input)\s+(.+)$", re.IGNORECASE)
        self._press_key_re = re.compile(r"^(?:press|hit)\s+(enter|return|space|spacebar|tab|escape|esc|backspace|delete|del|up|down|left|right|page\s*up|page\s*down|home|end)(?:\s+key)?$", re.IGNORECASE)
        self._scroll_re = re.compile(r"^(?:scroll\s+(up|down)(?:\s+(\d+))?)$", re.IGNORECASE)

        # 13. Scheduled Routines & Reminders
        self._routine_list_re = re.compile(r"^(?:list\s+routines|show\s+routines|my\s+routines|get\s+routines|show\s+scheduled\s+routines)$")
        self._routine_pause_all_re = re.compile(r"^(?:pause\s+all\s+routines|pause\s+routines|pause\s+scheduler)$")
        self._routine_resume_all_re = re.compile(r"^(?:resume\s+all\s+routines|resume\s+routines|resume\s+scheduler)$")
        self._routine_enable_sched_re = re.compile(r"^(?:enable\s+scheduler|start\s+scheduler)$")
        self._routine_disable_sched_re = re.compile(r"^(?:disable\s+scheduler|stop\s+scheduler)$")
        self._routine_pause_re = re.compile(r"^(?:pause\s+routine\s+(.+)|pause\s+(rtn_[a-zA-Z0-9]+))$")
        self._routine_resume_re = re.compile(r"^(?:resume\s+routine\s+(.+)|resume\s+(rtn_[a-zA-Z0-9]+))$")
        self._routine_delete_re = re.compile(r"^(?:delete\s+routine\s+(.+)|remove\s+routine\s+(.+))$")
        self._routine_run_now_re = re.compile(r"^(?:run\s+routine\s+(.+?)(?:\s+now)?|execute\s+routine\s+(.+?)(?:\s+now)?)$")
        self._reminder_at_re = re.compile(r"^(?:remind\s+me\s+at\s+(\d{1,2}:\d{2})\s+to\s+(.+)|remind\s+me\s+to\s+(.+)\s+at\s+(\d{1,2}:\d{2}))$")

        # 14. Phase 9 Task & Workflow Orchestration
        self._task_plan_re = re.compile(r"^(?:plan\s+task|orchestrate\s+task|create\s+workflow|plan\s+workflow)\s+(.+)$")
        self._task_run_re = re.compile(r"^(?:run\s+task\s+(.+)|execute\s+task\s+(.+)|start\s+task\s+(.+))$")
        self._task_pause_re = re.compile(r"^(?:pause\s+task\s+(.+))$")
        self._task_resume_re = re.compile(r"^(?:resume\s+task\s+(.+))$")
        self._task_cancel_re = re.compile(r"^(?:cancel\s+task\s+(.+)|abort\s+task\s+(.+))$")
        self._task_delete_re = re.compile(r"^(?:delete\s+task\s+(.+)|remove\s+task\s+(.+))$")
        self._task_status_re = re.compile(r"^(?:task\s+status\s+(.+)|show\s+task\s+(.+)|status\s+of\s+task\s+(.+))$")
        self._task_history_re = re.compile(r"^(?:task\s+history\s+(.+)|task\s+executions\s+(.+)|show\s+history\s+for\s+task\s+(.+))$")
        self._task_pause_all_re = re.compile(r"^(?:pause\s+all\s+tasks|pause\s+workflows)$")
        self._task_resume_all_re = re.compile(r"^(?:resume\s+all\s+tasks|resume\s+workflows)$")
        self._task_enable_re = re.compile(r"^(?:enable\s+tasks|enable\s+workflows)$")
        self._task_disable_re = re.compile(r"^(?:disable\s+tasks|disable\s+workflows)$")
        self._task_approve_re = re.compile(r"^(?:approve\s+step\s+(appr_[a-zA-Z0-9]+)|approve\s+(appr_[a-zA-Z0-9]+))$")
        self._task_reject_re = re.compile(r"^(?:reject\s+step\s+(appr_[a-zA-Z0-9]+)|reject\s+(appr_[a-zA-Z0-9]+))$")

        # 15. WhatsApp Messaging
        self._whatsapp_send_re1 = re.compile(
            r"^(?:open\s+whatsapp\s+and\s+)?send\s+(?:a\s+)?(?:whatsapp\s+)?(?:message|msg)?\s*(?:to\s+)?([a-zA-Z0-9_\s\+\-\.]+?)\s+on\s+whatsapp(?:\s+(?:saying|that\s+says|that|with\s+text|with\s+message)\s+|\s*:\s*)(.+)$",
            re.IGNORECASE,
        )
        self._whatsapp_send_re2 = re.compile(
            r"^(?:open\s+whatsapp\s+and\s+)?(?:tell|message)\s+([a-zA-Z0-9_\s\+\-\.]+?)\s+on\s+whatsapp(?:\s+(?:saying|that\s+says|that|with\s+text|with\s+message)\s+|\s*:\s*)(.+)$",
            re.IGNORECASE,
        )
        self._whatsapp_send_re3 = re.compile(
            r"^(?:open\s+whatsapp\s+and\s+)?send\s+(?:a\s+)?(?:whatsapp\s+)?(?:message|msg)\s+to\s+([a-zA-Z0-9_\s\+\-\.]+?)(?:\s+(?:saying|that\s+says|that|with\s+text|with\s+message)\s+|\s*:\s*)(.+)$",
            re.IGNORECASE,
        )
        self._whatsapp_send_re4 = re.compile(
            r"^(?:open\s+whatsapp\s+and\s+)?(?:send\s+(?:a\s+)?whatsapp\s+(?:message\s+)?to|whatsapp)\s+([a-zA-Z0-9_\s\+\-\.]+?)(?:\s+(?:saying|that\s+says|that|with\s+text|with\s+message)\s+|\s*:\s*)(.+)$",
            re.IGNORECASE,
        )
        self._whatsapp_send_re5 = re.compile(
            r"^(?:open\s+whatsapp\s+and\s+)?message\s+([a-zA-Z0-9_\s\+\-\.]+?)(?:\s+on\s+whatsapp)?(?:\s+(?:saying|that\s+says|that|with\s+text|with\s+message)\s+|\s*:\s*)(.+)$",
            re.IGNORECASE,
        )
        self._whatsapp_tell_re = re.compile(
            r"^(?:tell|ask)\s+([a-zA-Z0-9_\s\+\-]+?)\s+on\s+whatsapp\s+(?:that\s+|saying\s+|to\s+|:\s*)(.+)$",
            re.IGNORECASE,
        )
        self._whatsapp_message_on_re = re.compile(
            r"^(?:(?:send\s+(?:a\s+)?(?:whatsapp\s+)?(?:message|msg)\s+to|message|whatsapp)\s+([a-zA-Z0-9_\s\+\-]+?)\s+on\s+whatsapp(?:\s+(?:saying|that\s+says|with\s+text|with\s+message|that)\s+|\s*:\s*)(.+))$",
            re.IGNORECASE,
        )
        self._whatsapp_send_direct_re = re.compile(
            r"^(?:open\s+whatsapp\s+and\s+)?(?:send\s+(?:a\s+)?(?:whatsapp\s+)?(?:message|msg)\s+to|send\s+(?:a\s+)?whatsapp\s+to|message\s+(?:contact\s+)?|whatsapp\s+)([a-zA-Z0-9_\s\+\-]+?)(?:\s+(?:saying|that\s+says|with\s+text|with\s+message|that)\s+|\s*:\s*)(.+)$",
            re.IGNORECASE,
        )
        self._whatsapp_colon_re = re.compile(
            r"^(?:message|whatsapp|send\s+whatsapp\s+to)\s+([a-zA-Z0-9_\s\+\-]+?)\s*:\s*(.+)$",
            re.IGNORECASE,
        )

        # 16. Compound Routines & Macro Phrases
        self._compound_routine_direct_re = re.compile(
            r"^(?:(?:start|activate|trigger|run|enter|initiate)\s+)?(coding\s+mode|dev\s+mode|meeting\s+mode|morning\s+briefing|daily\s+briefing|focus\s+mode|deep\s+work|wrap\s+up\s+work|finish\s+work)$",
            re.IGNORECASE,
        )
        self._compound_routine_generic_re = re.compile(
            r"^(?:start|activate|trigger|run|execute)\s+(?:the\s+)?(?:routine|macro|workflow)\s+(.+?)(?:\s+now)?$",
            re.IGNORECASE,
        )

        # 17. Multimodal Screen Vision
        self._vision_screen_re = re.compile(
            r"^(?:(?:look\s+at\s+(?:my\s+)?screen(?:\s+and)?|what(?:'s|\s+is)\s+(?:on\s+)?(?:my\s+)?screen|analyze\s+(?:my\s+)?screen|explain\s+(?:what(?:'s|\s+is)\s+on\s+)?(?:my\s+)?screen|summarize\s+(?:my\s+)?screen|describe\s+(?:what\s+you\s+see\s+on\s+)?(?:my\s+)?screen|fix\s+(?:the\s+|this\s+)?error\s+(?:on\s+(?:my\s+)?screen)?|read\s+(?:my\s+)?screen|inspect\s+(?:my\s+)?screen)(?:\s+(.+))?)$",
            re.IGNORECASE,
        )

        # 18. Live Meeting Intelligence & Audio Transcription
        self._meeting_start_re = re.compile(
            r"^(?:start\s+meeting\s+notes|start\s+meeting\s+recording|transcribe\s+meeting|start\s+meeting\s+intelligence|record\s+meeting|start\s+meeting\s+mode\s+with\s+notes|take\s+meeting\s+notes)(?:\s+(?:titled|called|for)?\s*(.+))?$",
            re.IGNORECASE,
        )
        self._meeting_stop_re = re.compile(
            r"^(?:stop\s+meeting\s+notes|stop\s+meeting\s+recording|stop\s+meeting|end\s+meeting\s+notes|end\s+meeting|finish\s+meeting\s+notes|finish\s+meeting)$",
            re.IGNORECASE,
        )
        self._meeting_summary_re = re.compile(
            r"^(?:get\s+meeting\s+summary|show\s+meeting\s+summary|show\s+meeting\s+notes|summarize\s+meeting|meeting\s+summary|meeting\s+notes|get\s+meeting\s+notes)$",
            re.IGNORECASE,
        )

        # 19. Proactive Intelligence & Context Suggestions
        self._proactive_get_re = re.compile(
            r"^(?:(?:get|show|view|give\s+me)\s+(?:any\s+|my\s+)?(?:proactive\s+)?(?:suggestions|recommendations|briefing)|any\s+suggestions(?:\s+for\s+me)?|what\s+are\s+your\s+suggestions|proactive\s+briefing|proactive\s+suggestions|give\s+me\s+suggestions)$",
            re.IGNORECASE,
        )
        self._proactive_enable_re = re.compile(
            r"^(?:enable\s+proactive\s+mode|enable\s+proactive\s+suggestions|turn\s+on\s+proactive\s+mode|turn\s+on\s+proactive\s+suggestions|start\s+proactive\s+mode)$",
            re.IGNORECASE,
        )
        self._proactive_disable_re = re.compile(
            r"^(?:disable\s+proactive\s+mode|disable\s+proactive\s+suggestions|turn\s+off\s+proactive\s+mode|turn\s+off\s+proactive\s+suggestions|pause\s+proactive\s+mode|stop\s+proactive\s+mode)$",
            re.IGNORECASE,
        )
        self._proactive_dismiss_re = re.compile(
            r"^(?:dismiss\s+suggestions|dismiss\s+suggestion|clear\s+suggestions|clear\s+recommendations)$",
            re.IGNORECASE,
        )

        # 20. Playwright / CDP Deep Web Agent
        self._web_search_re = re.compile(
            r"^(?:(?:search\s+(?:the\s+)?web\s+for|search\s+google\s+for|search\s+online\s+for|look\s+up\s+online|web\s+search\s+for|search\s+for)\s+(.+)|search\s+(.+)\s+(?:on\s+the\s+web|online|on\s+google))$",
            re.IGNORECASE,
        )
        self._web_extract_re = re.compile(
            r"^(?:(?:read\s+webpage|extract\s+content\s+from|scrape\s+webpage|summarize\s+webpage|scrape\s+site|read\s+site)\s+(https?://\S+|www\.\S+|\S+\.\S+))$",
            re.IGNORECASE,
        )
        self._web_screenshot_re = re.compile(
            r"^(?:(?:take\s+screenshot\s+of\s+(?:website|webpage|page|site)|capture\s+(?:website|webpage|site)\s+screenshot|web\s+screenshot)\s+(https?://\S+|www\.\S+|\S+\.\S+))$",
            re.IGNORECASE,
        )

        # 21. Live Weather & Forecast
        self._weather_forecast_re = re.compile(
            r"^(?:(?:will\s+it\s+rain|weather\s+forecast|forecast|rain\s+forecast)(?:\s+(?:today|tomorrow|this\s+week))?(?:\s+(?:in|for|at)\s+(.+?))?|what(?:'s|\s+is)\s+(?:the\s+)?forecast(?:\s+(?:for|in|at)\s+(.+?))?)$",
            re.IGNORECASE,
        )
        self._weather_current_re = re.compile(
            r"^(?:(?:what(?:'s|\s+is)\s+(?:the\s+)?weather(?:\s+like)?(?:\s+(?:today|here|now|right\s+now))?|how(?:'s|\s+is)\s+(?:the\s+)?weather(?:\s+(?:today|here|now|right\s+now))?|weather(?:\s+(?:today|here|now|right\s+now))?|what\s+is\s+it\s+like\s+outside|how\s+is\s+it\s+outside)(?:\s+(?:in|for|at|around)\s+(.+?))?)$",
            re.IGNORECASE,
        )

        # 22. Fastest-Route Navigation & Directions
        self._directions_mode_switch_re = re.compile(
            r"^(?:(?:switch|change)(?:\s+mode)?\s+to\s+(walking|driving|cycling|transit|car|bike|bus|train)\s*(?:directions|route)?|actually\s+(walking|driving|cycling|transit|by\s+walk|by\s+car|by\s+bike))$",
            re.IGNORECASE,
        )
        self._directions_from_to_re = re.compile(
            r"^(?:(?:how\s+do\s+I\s+get|directions|fastest\s+route|route|navigate)\s+from\s+(.+?)\s+to\s+(.+?)(?:\s+by\s+(driving|walking|cycling|transit|car|bus|train|bike|bicycle))?)$",
            re.IGNORECASE,
        )
        self._directions_to_from_re = re.compile(
            r"^(?:(?:how\s+do\s+I\s+get|directions|fastest\s+route|route|navigate)\s+to\s+(.+?)\s+from\s+(.+?)(?:\s+by\s+(driving|walking|cycling|transit|car|bus|train|bike|bicycle))?)$",
            re.IGNORECASE,
        )
        self._navigation_to_re = re.compile(
            r"^(?:(?:navigate|directions|take\s+me|route)\s+to\s+(.+?)(?:\s+by\s+(driving|walking|cycling|transit|car|bus|train|bike|bicycle))?)$",
            re.IGNORECASE,
        )

        # 23. Saved Locations Memory
        self._location_save_re = re.compile(
            r"^(?:(?:remember\s+this\s+address\s+as|save\s+(?:location|address)\s+as|remember|save)\s+([a-zA-Z0-9_\-]+)\s*(?::|\s+as|\s+is)\s*(.+)|save\s+my\s+([a-zA-Z0-9_\-]+)\s+address\s*(?::|\s+as|\s+is)\s*(.+))$",
            re.IGNORECASE,
        )
        self._location_get_re = re.compile(
            r"^(?:what(?:'s|\s+is)\s+my\s+saved\s+([a-zA-Z0-9_\-]+)\s+(?:address|location)|get\s+saved\s+location\s+([a-zA-Z0-9_\-]+)|show\s+saved\s+locations|list\s+saved\s+locations|saved\s+locations)$",
            re.IGNORECASE,
        )
        self._location_delete_re = re.compile(
            r"^(?:forget\s+(?:my\s+saved\s+)?([a-zA-Z0-9_\-]+)\s+(?:location|address)|delete\s+saved\s+location\s+([a-zA-Z0-9_\-]+)|remove\s+saved\s+location\s+([a-zA-Z0-9_\-]+))$",
            re.IGNORECASE,
        )

        # 24. Live Current Location
        self._location_current_re = re.compile(
            r"^(?:where\s+am\s+i|what\s+is\s+my\s+current\s+location|show\s+my\s+(?:current\s+)?location|get\s+my\s+current\s+location|my\s+current\s+location|where\s+i\s+am|current\s+location)$",
            re.IGNORECASE,
        )
        self._location_save_current_re = re.compile(
            r"^(?:save\s+(?:my\s+)?current\s+location\s+as\s+([a-zA-Z0-9_\-]+)|remember\s+(?:my\s+)?current\s+location\s+as\s+([a-zA-Z0-9_\-]+)|save\s+where\s+i\s+am\s+as\s+([a-zA-Z0-9_\-]+)|set\s+(?:my\s+)?([a-zA-Z0-9_\-]+)\s+(?:as|to)\s+(?:my\s+)?current\s+location)(?:\s+(confirm|force))?$",
            re.IGNORECASE,
        )

        # 25. System Diagnosis & Auto-Repair
        self._system_repair_re = re.compile(
            r"^(?:(?:run\s+)?(?:system\s+)?(?:diagnosis\s+and\s+)?repair(?:\s+issues)?|repair\s+system(?:\s+issues)?|fix\s+system(?:\s+health|\s+issues)?|auto\s+repair\s+system|run\s+auto\s+repair|system\s+repair|diagnose\s+and\s+repair|repair\s+denver)$",
            re.IGNORECASE,
        )

        # 26. Voice Brevity & Response Style
        self._voice_brevity_re = re.compile(
            r"^(?:(?:set\s+voice\s+mode\s+to\s+|switch\s+to\s+|enable\s+)?(concise|detailed|brief|verbose)(?:\s+mode|\s+responses|\s+voice)?|be\s+(concise|detailed|brief|verbose))$",
            re.IGNORECASE,
        )

        # 27. Plugin Subsystem & Extensions
        self._plugin_list_re = re.compile(
            r"^(?:(?:list|show|get|display)\s+(?:all\s+)?(?:installed\s+)?plugins|installed\s+plugins|what\s+plugins\s+are\s+installed|show\s+extensions)$",
            re.IGNORECASE,
        )
        self._plugin_enable_re = re.compile(
            r"^(?:enable\s+plugin\s+([a-zA-Z0-9_\-]+)|activate\s+plugin\s+([a-zA-Z0-9_\-]+)|turn\s+on\s+plugin\s+([a-zA-Z0-9_\-]+))$",
            re.IGNORECASE,
        )
        self._plugin_disable_re = re.compile(
            r"^(?:disable\s+plugin\s+([a-zA-Z0-9_\-]+)|deactivate\s+plugin\s+([a-zA-Z0-9_\-]+)|turn\s+off\s+plugin\s+([a-zA-Z0-9_\-]+))$",
            re.IGNORECASE,
        )
        self._plugin_reload_re = re.compile(
            r"^(?:reload\s+plugins|refresh\s+plugins|rescan\s+plugins)$",
            re.IGNORECASE,
        )






    def route(self, normalized_text: str) -> CommandIntent:
        """Route normalized command string to corresponding CommandIntent."""
        text = normalized_text.strip()
        if not text or self._assistant_call_re.match(text):
            return CommandIntent(
                intent_name="assistant_call",
                action_name="assistant_call",
                category=CommandCategory.UTILITY,
                confidence=1.0,
                risk_level=CommandRiskLevel.SAFE,
            )

        # 1. Utility Check
        if self._time_re.match(text):
            return CommandIntent(
                intent_name="get_time",
                action_name="get_time",
                category=CommandCategory.UTILITY,
                confidence=1.0,
                risk_level=CommandRiskLevel.SAFE,
            )
        if self._date_re.match(text):
            return CommandIntent(
                intent_name="get_date",
                action_name="get_date",
                category=CommandCategory.UTILITY,
                confidence=1.0,
                risk_level=CommandRiskLevel.SAFE,
            )

        # 2. System Telemetry Check
        if self._sys_status_re.match(text):
            return CommandIntent(
                intent_name="get_system_status",
                action_name="get_system_status",
                category=CommandCategory.SYSTEM,
                confidence=1.0,
                risk_level=CommandRiskLevel.SAFE,
            )
        if self._system_repair_re.match(text):
            return CommandIntent(
                intent_name="system_repair",
                action_name="system_repair",
                category=CommandCategory.SYSTEM,
                confidence=1.0,
                risk_level=CommandRiskLevel.LOW,
            )
        m = self._voice_brevity_re.match(text)
        if m:
            raw_mode = (m.group(1) or m.group(2)).strip().lower()
            mode = "concise" if raw_mode in ("concise", "brief") else "detailed"
            return CommandIntent(
                intent_name="set_voice_brevity",
                action_name="set_voice_brevity",
                category=CommandCategory.SYSTEM,
                confidence=1.0,
                params={"mode": mode},
                risk_level=CommandRiskLevel.SAFE,
            )

        # 2.5 Plugin Subsystem Check
        if self._plugin_list_re.match(text):
            return CommandIntent(
                intent_name="list_plugins",
                action_name="list_plugins",
                category=CommandCategory.SYSTEM,
                confidence=1.0,
                risk_level=CommandRiskLevel.SAFE,
            )
        m = self._plugin_enable_re.match(text)
        if m:
            p_id = (m.group(1) or m.group(2) or m.group(3)).strip()
            return CommandIntent(
                intent_name="enable_plugin",
                action_name="enable_plugin",
                category=CommandCategory.SYSTEM,
                confidence=1.0,
                params={"plugin_id": p_id},
                risk_level=CommandRiskLevel.LOW,
            )
        m = self._plugin_disable_re.match(text)
        if m:
            p_id = (m.group(1) or m.group(2) or m.group(3)).strip()
            return CommandIntent(
                intent_name="disable_plugin",
                action_name="disable_plugin",
                category=CommandCategory.SYSTEM,
                confidence=1.0,
                params={"plugin_id": p_id},
                risk_level=CommandRiskLevel.LOW,
            )
        if self._plugin_reload_re.match(text):
            return CommandIntent(
                intent_name="reload_plugins",
                action_name="reload_plugins",
                category=CommandCategory.SYSTEM,
                confidence=1.0,
                risk_level=CommandRiskLevel.LOW,
            )
        if self._cpu_re.match(text):
            return CommandIntent(
                intent_name="get_cpu",
                action_name="get_cpu",
                category=CommandCategory.SYSTEM,
                confidence=1.0,
                risk_level=CommandRiskLevel.SAFE,
            )
        if self._ram_re.match(text):
            return CommandIntent(
                intent_name="get_ram",
                action_name="get_ram",
                category=CommandCategory.SYSTEM,
                confidence=1.0,
                risk_level=CommandRiskLevel.SAFE,
            )
        if self._battery_re.match(text):
            return CommandIntent(
                intent_name="get_battery",
                action_name="get_battery",
                category=CommandCategory.SYSTEM,
                confidence=1.0,
                risk_level=CommandRiskLevel.SAFE,
            )

        # 3. Preference Settings Check (Before general memory)
        m = self._pref_set_fav_re.match(text)
        if m:
            key, val = m.group(1).strip().lower(), m.group(2).strip()
            return CommandIntent(
                intent_name="set_preference",
                action_name="set_preference",
                category=CommandCategory.MEMORY,
                confidence=1.0,
                params={"key": f"favorite_{key}", "value": val, "category": "general"},
                risk_level=CommandRiskLevel.LOW,
            )

        m = self._pref_set_re.match(text)
        if m:
            key, val = m.group(1).strip().lower(), m.group(2).strip()
            return CommandIntent(
                intent_name="set_preference",
                action_name="set_preference",
                category=CommandCategory.MEMORY,
                confidence=1.0,
                params={"key": key, "value": val, "category": "general"},
                risk_level=CommandRiskLevel.LOW,
            )

        m = self._pref_get_fav_re.match(text)
        if m:
            key = (m.group(1) or m.group(2)).strip().lower()
            return CommandIntent(
                intent_name="get_preference",
                action_name="get_preference",
                category=CommandCategory.MEMORY,
                confidence=1.0,
                params={"key": f"favorite_{key}" if m.group(1) else key},
                risk_level=CommandRiskLevel.SAFE,
            )

        # 4. Note Management Check
        if self._note_list_re.match(text):
            return CommandIntent(
                intent_name="list_notes",
                action_name="list_notes",
                category=CommandCategory.NOTE,
                confidence=1.0,
                risk_level=CommandRiskLevel.SAFE,
            )

        m = self._note_search_re.match(text)
        if m:
            query = m.group(1).strip()
            return CommandIntent(
                intent_name="search_notes",
                action_name="search_notes",
                category=CommandCategory.NOTE,
                confidence=1.0,
                params={"query": query},
                risk_level=CommandRiskLevel.SAFE,
            )

        m = self._note_create_colon_re.match(text)
        if m:
            title, content = m.group(1).strip().lower(), m.group(2).strip()
            return CommandIntent(
                intent_name="create_note",
                action_name="create_note",
                category=CommandCategory.NOTE,
                confidence=1.0,
                params={"title": title, "content": content},
                risk_level=CommandRiskLevel.LOW,
            )

        m = self._note_create_re.match(text)
        if m:
            title = m.group(1).strip().lower() if m.group(1) else ""
            content = m.group(2).strip()
            return CommandIntent(
                intent_name="create_note",
                action_name="create_note",
                category=CommandCategory.NOTE,
                confidence=1.0,
                params={"title": title, "content": content},
                risk_level=CommandRiskLevel.LOW,
            )

        # 5. Task Management & Orchestration Check (Phase 9 & Phase 1)
        m = self._task_plan_re.match(text)
        if m:
            plan_text = m.group(1).strip()
            return CommandIntent(
                intent_name="plan_task",
                action_name="plan_task",
                category=CommandCategory.TASK,
                confidence=1.0,
                params={"plan_text": plan_text},
                risk_level=CommandRiskLevel.LOW,
            )

        m = self._task_run_re.match(text)
        if m:
            target = (m.group(1) or m.group(2) or m.group(3)).strip()
            return CommandIntent(
                intent_name="run_task",
                action_name="run_task",
                category=CommandCategory.TASK,
                confidence=1.0,
                params={"task_id": target},
                risk_level=CommandRiskLevel.MEDIUM,
            )

        m = self._task_pause_re.match(text)
        if m:
            target = m.group(1).strip()
            return CommandIntent(
                intent_name="pause_task",
                action_name="pause_task",
                category=CommandCategory.TASK,
                confidence=1.0,
                params={"task_id": target},
                risk_level=CommandRiskLevel.LOW,
            )

        m = self._task_resume_re.match(text)
        if m:
            target = m.group(1).strip()
            return CommandIntent(
                intent_name="resume_task",
                action_name="resume_task",
                category=CommandCategory.TASK,
                confidence=1.0,
                params={"task_id": target},
                risk_level=CommandRiskLevel.LOW,
            )

        m = self._task_cancel_re.match(text)
        if m:
            target = (m.group(1) or m.group(2)).strip()
            return CommandIntent(
                intent_name="cancel_task",
                action_name="cancel_task",
                category=CommandCategory.TASK,
                confidence=1.0,
                params={"task_id": target},
                risk_level=CommandRiskLevel.LOW,
            )

        m = self._task_delete_re.match(text)
        if m:
            target = (m.group(1) or m.group(2)).strip()
            return CommandIntent(
                intent_name="delete_task",
                action_name="delete_task",
                category=CommandCategory.TASK,
                confidence=1.0,
                params={"task_id": target},
                risk_level=CommandRiskLevel.MEDIUM,
            )

        m = self._task_status_re.match(text)
        if m:
            target = (m.group(1) or m.group(2) or m.group(3)).strip()
            return CommandIntent(
                intent_name="show_task_status",
                action_name="show_task_status",
                category=CommandCategory.TASK,
                confidence=1.0,
                params={"task_id": target},
                risk_level=CommandRiskLevel.SAFE,
            )

        m = self._task_history_re.match(text)
        if m:
            target = (m.group(1) or m.group(2) or m.group(3)).strip()
            return CommandIntent(
                intent_name="show_task_history",
                action_name="show_task_history",
                category=CommandCategory.TASK,
                confidence=1.0,
                params={"task_id": target},
                risk_level=CommandRiskLevel.SAFE,
            )

        if self._task_pause_all_re.match(text):
            return CommandIntent(
                intent_name="pause_all_tasks",
                action_name="pause_all_tasks",
                category=CommandCategory.TASK,
                confidence=1.0,
                risk_level=CommandRiskLevel.LOW,
            )

        if self._task_resume_all_re.match(text):
            return CommandIntent(
                intent_name="resume_all_tasks",
                action_name="resume_all_tasks",
                category=CommandCategory.TASK,
                confidence=1.0,
                risk_level=CommandRiskLevel.LOW,
            )

        if self._task_enable_re.match(text):
            return CommandIntent(
                intent_name="enable_tasks",
                action_name="enable_tasks",
                category=CommandCategory.TASK,
                confidence=1.0,
                risk_level=CommandRiskLevel.LOW,
            )

        if self._task_disable_re.match(text):
            return CommandIntent(
                intent_name="disable_tasks",
                action_name="disable_tasks",
                category=CommandCategory.TASK,
                confidence=1.0,
                risk_level=CommandRiskLevel.LOW,
            )

        m = self._task_approve_re.match(text)
        if m:
            appr_id = (m.group(1) or m.group(2)).strip()
            return CommandIntent(
                intent_name="approve_task_step",
                action_name="approve_task_step",
                category=CommandCategory.TASK,
                confidence=1.0,
                params={"approval_id": appr_id},
                risk_level=CommandRiskLevel.MEDIUM,
            )

        m = self._task_reject_re.match(text)
        if m:
            appr_id = (m.group(1) or m.group(2)).strip()
            return CommandIntent(
                intent_name="reject_task_step",
                action_name="reject_task_step",
                category=CommandCategory.TASK,
                confidence=1.0,
                params={"approval_id": appr_id},
                risk_level=CommandRiskLevel.LOW,
            )

        if self._task_list_re.match(text):
            return CommandIntent(
                intent_name="list_tasks",
                action_name="list_tasks",
                category=CommandCategory.TASK,
                confidence=1.0,
                risk_level=CommandRiskLevel.SAFE,
            )

        m = self._task_complete_re.match(text)
        if m:
            raw_id = m.group(1) or m.group(2) or m.group(3)
            task_id = int(raw_id) if raw_id and raw_id.isdigit() else 1
            return CommandIntent(
                intent_name="complete_task",
                action_name="complete_task",
                category=CommandCategory.TASK,
                confidence=1.0,
                params={"task_id": task_id},
                risk_level=CommandRiskLevel.MEDIUM,
            )

        m = self._task_create_re.match(text)
        if m:
            task_text = m.group(1).strip()
            return CommandIntent(
                intent_name="create_task",
                action_name="create_task",
                category=CommandCategory.TASK,
                confidence=1.0,
                params={"task_text": task_text},
                risk_level=CommandRiskLevel.LOW,
            )

        # 5.5 Saved Locations Memory (Check before generic memory remember/recall)
        m = self._location_current_re.match(text)
        if m:
            return CommandIntent(
                intent_name="get_current_location",
                action_name="get_current_location",
                category=CommandCategory.UTILITY,
                confidence=1.0,
                params={},
                risk_level=CommandRiskLevel.SAFE,
            )

        m = self._location_save_current_re.match(text)
        if m:
            label = (m.group(1) or m.group(2) or m.group(3) or m.group(4) or "").strip().lower()
            confirmed = bool(m.group(5))
            return CommandIntent(
                intent_name="save_current_location",
                action_name="save_current_location",
                category=CommandCategory.MEMORY,
                confidence=1.0,
                params={"label": label, "confirmed": confirmed, "force": confirmed},
                risk_level=CommandRiskLevel.LOW,
            )

        m = self._location_save_re.match(text)
        if m:
            label = (m.group(1) or m.group(3) or "").strip().lower()
            addr = (m.group(2) or m.group(4) or "").strip()
            return CommandIntent(
                intent_name="save_location",
                action_name="save_location",
                category=CommandCategory.MEMORY,
                confidence=1.0,
                params={"label": label, "raw_address": addr},
                risk_level=CommandRiskLevel.LOW,
            )

        m = self._location_get_re.match(text)
        if m:
            label = (m.group(1) or m.group(2) or "").strip().lower()
            return CommandIntent(
                intent_name="get_saved_location",
                action_name="get_saved_location",
                category=CommandCategory.MEMORY,
                confidence=1.0,
                params={"label": label},
                risk_level=CommandRiskLevel.SAFE,
            )

        m = self._location_delete_re.match(text)
        if m:
            label = (m.group(1) or m.group(2) or m.group(3) or "").strip().lower()
            return CommandIntent(
                intent_name="delete_saved_location",
                action_name="delete_saved_location",
                category=CommandCategory.MEMORY,
                confidence=1.0,
                params={"label": label},
                risk_level=CommandRiskLevel.LOW,
            )

        # 6. Memory & Recall Check
        m = self._mem_remember_re.match(text)
        if m:
            fact = m.group(1).strip()
            return CommandIntent(
                intent_name="remember",
                action_name="remember",
                category=CommandCategory.MEMORY,
                confidence=1.0,
                params={"content": fact, "key": f"mem_{abs(hash(fact)) % 100000}", "category": "user_memory"},
                risk_level=CommandRiskLevel.LOW,
            )

        m = self._mem_recall_re.match(text)
        if m:
            query = m.group(1).strip()
            return CommandIntent(
                intent_name="recall_memory",
                action_name="recall_memory",
                category=CommandCategory.MEMORY,
                confidence=1.0,
                params={"query": query},
                risk_level=CommandRiskLevel.SAFE,
            )

        m = self._mem_query_extra_re.match(text)
        if m:
            query = text.strip()
            return CommandIntent(
                intent_name="recall_memory",
                action_name="recall_memory",
                category=CommandCategory.MEMORY,
                confidence=1.0,
                params={"query": query},
                risk_level=CommandRiskLevel.SAFE,
            )

        m = self._mem_forget_re.match(text)
        if m:
            query = m.group(1).strip()
            return CommandIntent(
                intent_name="forget_memory",
                action_name="forget_memory",
                category=CommandCategory.MEMORY,
                confidence=1.0,
                params={"query": query},
                risk_level=CommandRiskLevel.MEDIUM,
            )

        if self._mem_export_re.match(text):
            return CommandIntent(
                intent_name="export_memory",
                action_name="export_memory",
                category=CommandCategory.MEMORY,
                confidence=1.0,
                params={},
                risk_level=CommandRiskLevel.SAFE,
            )

        if self._mem_clear_notes_re.match(text):
            return CommandIntent(
                intent_name="clear_all_notes",
                action_name="clear_all_notes",
                category=CommandCategory.MEMORY,
                confidence=1.0,
                params={},
                risk_level=CommandRiskLevel.HIGH,
            )

        if self._mem_list_re.match(text):
            return CommandIntent(
                intent_name="list_memories",
                action_name="list_memories",
                category=CommandCategory.MEMORY,
                confidence=1.0,
                params={},
                risk_level=CommandRiskLevel.SAFE,
            )

        m = self._pref_set_fav_re.match(text)
        if m:
            key = m.group(1).strip()
            val = m.group(2).strip()
            return CommandIntent(
                intent_name="set_preference",
                action_name="set_preference",
                category=CommandCategory.MEMORY,
                confidence=1.0,
                params={"key": key, "value": val, "preference_key": key, "preference_value": val},
                risk_level=CommandRiskLevel.LOW,
            )

        m = self._pref_set_re.match(text)
        if m:
            key = m.group(1).strip()
            val = m.group(2).strip()
            return CommandIntent(
                intent_name="set_preference",
                action_name="set_preference",
                category=CommandCategory.MEMORY,
                confidence=1.0,
                params={"key": key, "value": val, "preference_key": key, "preference_value": val},
                risk_level=CommandRiskLevel.LOW,
            )

        m = self._pref_get_fav_re.match(text)
        if m:
            key = (m.group(1) or m.group(2)).strip()
            return CommandIntent(
                intent_name="get_preference",
                action_name="get_preference",
                category=CommandCategory.MEMORY,
                confidence=1.0,
                params={"key": key, "preference_key": key},
                risk_level=CommandRiskLevel.SAFE,
            )

        if self._pref_list_re.match(text):
            return CommandIntent(
                intent_name="list_preferences",
                action_name="list_preferences",
                category=CommandCategory.MEMORY,
                confidence=1.0,
                risk_level=CommandRiskLevel.SAFE,
            )

        if self._clear_context_re.match(text):
            return CommandIntent(
                intent_name="clear_context",
                action_name="clear_context",
                category=CommandCategory.MEMORY,
                confidence=1.0,
                risk_level=CommandRiskLevel.SAFE,
            )


        # 7. Confirmation Checks
        m = self._confirm_re.match(text)
        if m:
            token = m.group(1) if m.groups() and m.group(1) else ""
            return CommandIntent(
                intent_name="confirm_action",
                action_name="confirm_action",
                category=CommandCategory.UTILITY,
                confidence=1.0,
                params={"token": token},
                risk_level=CommandRiskLevel.SAFE,
            )

        if self._cancel_re.match(text):
            return CommandIntent(
                intent_name="cancel_action",
                action_name="cancel_action",
                category=CommandCategory.UTILITY,
                confidence=1.0,
                risk_level=CommandRiskLevel.SAFE,
            )

        # 7.5 Compound Routines & Macros
        m = self._compound_routine_direct_re.match(text)
        if m:
            routine_phrase = m.group(1).strip()
            return CommandIntent(
                intent_name="run_routine_now",
                action_name="run_routine_now",
                category=CommandCategory.ROUTINE,
                confidence=1.0,
                params={"routine_id": routine_phrase},
                risk_level=CommandRiskLevel.MEDIUM,
            )

        m = self._compound_routine_generic_re.match(text)
        if m:
            routine_phrase = m.group(1).strip()
            if routine_phrase.lower().endswith(" now"):
                routine_phrase = routine_phrase[:-4].strip()
            return CommandIntent(
                intent_name="run_routine_now",
                action_name="run_routine_now",
                category=CommandCategory.ROUTINE,
                confidence=1.0,
                params={"routine_id": routine_phrase},
                risk_level=CommandRiskLevel.MEDIUM,
            )

        # 7.8 Multimodal Screen Vision
        m = self._vision_screen_re.match(text)
        if m:
            query = m.group(1).strip() if m.groups() and m.group(1) else "Describe what you see on my screen and diagnose any issues or errors."
            if not query:
                query = "Describe what you see on my screen and diagnose any issues or errors."

            focus = "general"
            text_lower = text.lower()
            if any(k in text_lower for k in ["error", "fix", "bug", "trace", "fail", "broken", "issue", "wrong"]):
                focus = "error_diagnosis"
            elif any(k in text_lower for k in ["read", "ocr", "text on", "transcribe", "copy"]):
                focus = "ocr_reading"
            elif any(k in text_lower for k in ["summarize", "overview", "summary", "brief"]):
                focus = "summary"

            return CommandIntent(
                intent_name="analyze_screen",
                action_name="analyze_screen",
                category=CommandCategory.SYSTEM,
                confidence=1.0,
                params={"prompt": query, "focus_mode": focus},
                risk_level=CommandRiskLevel.LOW,
            )

        # 7.9 Live Meeting Intelligence & Audio Transcription
        m = self._meeting_start_re.match(text)
        if m:
            title = m.group(1).strip() if m.groups() and m.group(1) else "Live Meeting"
            return CommandIntent(
                intent_name="start_meeting_notes",
                action_name="start_meeting_notes",
                category=CommandCategory.SYSTEM,
                confidence=1.0,
                params={"title": title},
                risk_level=CommandRiskLevel.LOW,
            )

        if self._meeting_stop_re.match(text):
            return CommandIntent(
                intent_name="stop_meeting_notes",
                action_name="stop_meeting_notes",
                category=CommandCategory.SYSTEM,
                confidence=1.0,
                risk_level=CommandRiskLevel.LOW,
            )

        if self._meeting_summary_re.match(text):
            return CommandIntent(
                intent_name="get_meeting_summary",
                action_name="get_meeting_summary",
                category=CommandCategory.SYSTEM,
                confidence=1.0,
                risk_level=CommandRiskLevel.SAFE,
            )

        # 7.10 Proactive Intelligence & Context Suggestions
        if self._proactive_get_re.match(text):
            return CommandIntent(
                intent_name="get_proactive_suggestions",
                action_name="get_proactive_suggestions",
                category=CommandCategory.UTILITY,
                confidence=1.0,
                risk_level=CommandRiskLevel.SAFE,
            )

        if self._proactive_enable_re.match(text):
            return CommandIntent(
                intent_name="set_proactive_mode",
                action_name="set_proactive_mode",
                category=CommandCategory.UTILITY,
                confidence=1.0,
                params={"enabled": True},
                risk_level=CommandRiskLevel.LOW,
            )

        if self._proactive_disable_re.match(text):
            return CommandIntent(
                intent_name="set_proactive_mode",
                action_name="set_proactive_mode",
                category=CommandCategory.UTILITY,
                confidence=1.0,
                params={"enabled": False},
                risk_level=CommandRiskLevel.LOW,
            )

        if self._proactive_dismiss_re.match(text):
            return CommandIntent(
                intent_name="dismiss_proactive_suggestions",
                action_name="dismiss_proactive_suggestions",
                category=CommandCategory.UTILITY,
                confidence=1.0,
                risk_level=CommandRiskLevel.SAFE,
            )

        # 7.11 Playwright / CDP Deep Web Agent
        m = self._web_search_re.match(text)
        if m:
            query = (m.group(1) or m.group(2) or "").strip()
            return CommandIntent(
                intent_name="web_search_query",
                action_name="web_search_query",
                category=CommandCategory.UTILITY,
                confidence=1.0,
                params={"query": query},
                risk_level=CommandRiskLevel.SAFE,
            )

        m = self._web_extract_re.match(text)
        if m:
            url = m.group(1).strip()
            return CommandIntent(
                intent_name="extract_web_page",
                action_name="extract_web_page",
                category=CommandCategory.UTILITY,
                confidence=1.0,
                params={"url": url},
                risk_level=CommandRiskLevel.SAFE,
            )

        m = self._web_screenshot_re.match(text)
        if m:
            url = m.group(1).strip()
            return CommandIntent(
                intent_name="capture_web_screenshot",
                action_name="capture_web_screenshot",
                category=CommandCategory.SYSTEM,
                confidence=1.0,
                params={"url": url},
                risk_level=CommandRiskLevel.MEDIUM,
            )

        # 8. Screenshot Check
        if self._screenshot_re.match(text):
            return CommandIntent(
                intent_name="take_screenshot",
                action_name="take_screenshot",
                category=CommandCategory.SYSTEM,
                confidence=1.0,
                risk_level=CommandRiskLevel.MEDIUM,
            )

        # 8.5 Live Weather & Forecast
        m = self._weather_forecast_re.match(text)
        if m:
            city = (m.group(1) or m.group(2) or "").strip()
            return CommandIntent(
                intent_name="get_weather_forecast",
                action_name="get_weather_forecast",
                category=CommandCategory.UTILITY,
                confidence=1.0,
                params={"city": city, "days": 1},
                risk_level=CommandRiskLevel.SAFE,
            )

        m = self._weather_current_re.match(text)
        if m:
            city = (m.group(1) or "").strip()
            return CommandIntent(
                intent_name="get_weather",
                action_name="get_weather",
                category=CommandCategory.UTILITY,
                confidence=1.0,
                params={"city": city},
                risk_level=CommandRiskLevel.SAFE,
            )

        # 8.6 Fastest-Route Navigation & Directions
        m = self._directions_mode_switch_re.match(text)
        if m:
            mode_raw = (m.group(1) or m.group(2) or "driving").strip()
            mode_clean = "walking" if "walk" in mode_raw.lower() else ("cycling" if "bike" in mode_raw.lower() or "cycling" in mode_raw.lower() else ("transit" if "transit" in mode_raw.lower() or "bus" in mode_raw.lower() or "train" in mode_raw.lower() else "driving"))
            return CommandIntent(
                intent_name="switch_directions_mode",
                action_name="switch_directions_mode",
                category=CommandCategory.APPLICATION,
                confidence=1.0,
                params={"mode": mode_clean},
                risk_level=CommandRiskLevel.SAFE,
            )

        m = self._directions_from_to_re.match(text)
        if m:
            orig = m.group(1).strip()
            dest = m.group(2).strip()
            mode_raw = m.group(3) or "driving"
            mode_clean = "walking" if "walk" in mode_raw.lower() else ("cycling" if "bike" in mode_raw.lower() or "cycling" in mode_raw.lower() else ("transit" if "transit" in mode_raw.lower() or "bus" in mode_raw.lower() or "train" in mode_raw.lower() else "driving"))
            return CommandIntent(
                intent_name="get_directions",
                action_name="get_directions",
                category=CommandCategory.APPLICATION,
                confidence=1.0,
                params={"origin": orig, "destination": dest, "mode": mode_clean},
                risk_level=CommandRiskLevel.SAFE,
            )

        m = self._directions_to_from_re.match(text)
        if m:
            dest = m.group(1).strip()
            orig = m.group(2).strip()
            mode_raw = m.group(3) or "driving"
            mode_clean = "walking" if "walk" in mode_raw.lower() else ("cycling" if "bike" in mode_raw.lower() or "cycling" in mode_raw.lower() else ("transit" if "transit" in mode_raw.lower() or "bus" in mode_raw.lower() or "train" in mode_raw.lower() else "driving"))
            return CommandIntent(
                intent_name="get_directions",
                action_name="get_directions",
                category=CommandCategory.APPLICATION,
                confidence=1.0,
                params={"origin": orig, "destination": dest, "mode": mode_clean},
                risk_level=CommandRiskLevel.SAFE,
            )

        m = self._navigation_to_re.match(text)
        if m:
            dest = m.group(1).strip()
            mode_raw = m.group(2) or "driving"
            mode_clean = "walking" if "walk" in mode_raw.lower() else ("cycling" if "bike" in mode_raw.lower() or "cycling" in mode_raw.lower() else ("transit" if "transit" in mode_raw.lower() or "bus" in mode_raw.lower() or "train" in mode_raw.lower() else "driving"))
            return CommandIntent(
                intent_name="navigate_to",
                action_name="navigate_to",
                category=CommandCategory.APPLICATION,
                confidence=1.0,
                params={"destination": dest, "mode": mode_clean},
                risk_level=CommandRiskLevel.SAFE,
            )

        # 9. Window Management Checks
        if self._win_desktop_re.match(text):
            return CommandIntent(
                intent_name="show_desktop",
                action_name="show_desktop",
                category=CommandCategory.APPLICATION,
                confidence=1.0,
                risk_level=CommandRiskLevel.MEDIUM,
            )

        m = self._win_minimize_re.match(text)
        if m:
            win_name = (m.group(1) or m.group(2)).strip()
            return CommandIntent(
                intent_name="minimize_window",
                action_name="minimize_window",
                category=CommandCategory.APPLICATION,
                confidence=1.0,
                params={"window": win_name},
                risk_level=CommandRiskLevel.MEDIUM,
            )

        m = self._win_maximize_re.match(text)
        if m:
            win_name = (m.group(1) or m.group(2)).strip()
            return CommandIntent(
                intent_name="maximize_window",
                action_name="maximize_window",
                category=CommandCategory.APPLICATION,
                confidence=1.0,
                params={"window": win_name},
                risk_level=CommandRiskLevel.MEDIUM,
            )

        m = self._win_restore_re.match(text)
        if m:
            win_name = (m.group(1) or m.group(2)).strip()
            return CommandIntent(
                intent_name="restore_window",
                action_name="restore_window",
                category=CommandCategory.APPLICATION,
                confidence=1.0,
                params={"window": win_name},
                risk_level=CommandRiskLevel.MEDIUM,
            )

        m = self._win_focus_re.match(text)
        if m:
            win_name = (m.group(1) or m.group(2) or m.group(3)).strip()
            return CommandIntent(
                intent_name="focus_window",
                action_name="focus_window",
                category=CommandCategory.APPLICATION,
                confidence=1.0,
                params={"window": win_name},
                risk_level=CommandRiskLevel.MEDIUM,
            )

        # 10. Volume Control Checks
        if self._vol_mute_re.match(text):
            return CommandIntent(
                intent_name="mute_volume",
                action_name="mute_volume",
                category=CommandCategory.SYSTEM,
                confidence=1.0,
                risk_level=CommandRiskLevel.MEDIUM,
            )

        if self._vol_unmute_re.match(text):
            return CommandIntent(
                intent_name="unmute_volume",
                action_name="unmute_volume",
                category=CommandCategory.SYSTEM,
                confidence=1.0,
                risk_level=CommandRiskLevel.MEDIUM,
            )

        if self._vol_get_re.match(text):
            return CommandIntent(
                intent_name="get_volume",
                action_name="get_volume",
                category=CommandCategory.SYSTEM,
                confidence=1.0,
                risk_level=CommandRiskLevel.SAFE,
            )

        m = self._vol_set_re.match(text)
        if m:
            val = int(m.group(1) or m.group(2))
            return CommandIntent(
                intent_name="set_volume",
                action_name="set_volume",
                category=CommandCategory.SYSTEM,
                confidence=1.0,
                params={"value": val},
                risk_level=CommandRiskLevel.MEDIUM,
            )

        m = self._vol_inc_re.match(text)
        if m:
            step = int(m.group(1)) if m.group(1) else 10
            return CommandIntent(
                intent_name="increase_volume",
                action_name="increase_volume",
                category=CommandCategory.SYSTEM,
                confidence=1.0,
                params={"step": step},
                risk_level=CommandRiskLevel.MEDIUM,
            )

        m = self._vol_dec_re.match(text)
        if m:
            step = int(m.group(1)) if m.group(1) else 10
            return CommandIntent(
                intent_name="decrease_volume",
                action_name="decrease_volume",
                category=CommandCategory.SYSTEM,
                confidence=1.0,
                params={"step": step},
                risk_level=CommandRiskLevel.MEDIUM,
            )

        # 11. System Summary & Lock Workstation
        if self._sys_summary_re.match(text):
            return CommandIntent(
                intent_name="get_system_summary",
                action_name="get_system_summary",
                category=CommandCategory.SYSTEM,
                confidence=1.0,
                risk_level=CommandRiskLevel.SAFE,
            )

        if self._lock_ws_re.match(text):
            return CommandIntent(
                intent_name="lock_workstation",
                action_name="lock_workstation",
                category=CommandCategory.SYSTEM,
                confidence=1.0,
                risk_level=CommandRiskLevel.HIGH,
                requires_confirmation=False,
            )

        if self._sleep_re.match(text):
            return CommandIntent(
                intent_name="enter_sleep_mode",
                action_name="enter_sleep_mode",
                category=CommandCategory.SYSTEM,
                confidence=1.0,
                risk_level=CommandRiskLevel.SAFE,
                requires_confirmation=False,
            )

        if self._wake_re.match(text):
            return CommandIntent(
                intent_name="wake_up",
                action_name="wake_up",
                category=CommandCategory.SYSTEM,
                confidence=1.0,
                risk_level=CommandRiskLevel.SAFE,
                requires_confirmation=False,
            )

        # 11b. Clipboard & Typing Controls
        if self._clipboard_summary_re.match(text):
            return CommandIntent(
                intent_name="summarize_clipboard",
                action_name="summarize_clipboard",
                category=CommandCategory.UTILITY,
                confidence=1.0,
                risk_level=CommandRiskLevel.SAFE,
            )

        if self._clipboard_read_re.match(text):
            return CommandIntent(
                intent_name="read_clipboard",
                action_name="read_clipboard",
                category=CommandCategory.UTILITY,
                confidence=1.0,
                risk_level=CommandRiskLevel.SAFE,
            )

        m = self._type_text_re.match(text)
        if m:
            text_to_type = m.group(1).strip()
            return CommandIntent(
                intent_name="type_text",
                action_name="type_text",
                category=CommandCategory.SYSTEM,
                confidence=1.0,
                params={"text": text_to_type},
                risk_level=CommandRiskLevel.LOW,
            )

        m = self._press_key_re.match(text)
        if m:
            key_name = m.group(1).strip().lower()
            return CommandIntent(
                intent_name="press_key",
                action_name="press_key",
                category=CommandCategory.SYSTEM,
                confidence=1.0,
                params={"key": key_name},
                risk_level=CommandRiskLevel.LOW,
            )

        m = self._scroll_re.match(text)
        if m:
            direction = (m.group(1) or "down").strip().lower()
            steps = int(m.group(2)) if m.group(2) else 5
            return CommandIntent(
                intent_name="scroll_window",
                action_name="scroll_window",
                category=CommandCategory.SYSTEM,
                confidence=1.0,
                params={"direction": direction, "steps": steps},
                risk_level=CommandRiskLevel.LOW,
            )

        # 12. Browser & Web Navigation
        m = self._browser_open_re.match(text)
        if m:
            target = (m.group(1) or m.group(2) or m.group(3) or m.group(4)).strip()
            return CommandIntent(
                intent_name="open_browser",
                action_name="open_browser",
                category=CommandCategory.APPLICATION,
                confidence=1.0,
                params={"target": target},
                risk_level=CommandRiskLevel.LOW,
            )

        # 13. Scheduled Routines & Reminders
        if self._routine_list_re.match(text):
            return CommandIntent(
                intent_name="list_routines",
                action_name="list_routines",
                category=CommandCategory.ROUTINE,
                confidence=1.0,
                risk_level=CommandRiskLevel.SAFE,
            )

        if self._routine_pause_all_re.match(text):
            return CommandIntent(
                intent_name="pause_scheduler",
                action_name="pause_scheduler",
                category=CommandCategory.ROUTINE,
                confidence=1.0,
                risk_level=CommandRiskLevel.LOW,
            )

        if self._routine_resume_all_re.match(text):
            return CommandIntent(
                intent_name="resume_scheduler",
                action_name="resume_scheduler",
                category=CommandCategory.ROUTINE,
                confidence=1.0,
                risk_level=CommandRiskLevel.LOW,
            )

        if self._routine_enable_sched_re.match(text):
            return CommandIntent(
                intent_name="enable_scheduler",
                action_name="enable_scheduler",
                category=CommandCategory.ROUTINE,
                confidence=1.0,
                risk_level=CommandRiskLevel.LOW,
            )

        if self._routine_disable_sched_re.match(text):
            return CommandIntent(
                intent_name="disable_scheduler",
                action_name="disable_scheduler",
                category=CommandCategory.ROUTINE,
                confidence=1.0,
                risk_level=CommandRiskLevel.LOW,
            )

        m = self._routine_pause_re.match(text)
        if m:
            target = (m.group(1) or m.group(2)).strip()
            return CommandIntent(
                intent_name="pause_routine",
                action_name="pause_routine",
                category=CommandCategory.ROUTINE,
                confidence=1.0,
                params={"routine_id": target},
                risk_level=CommandRiskLevel.LOW,
            )

        m = self._routine_resume_re.match(text)
        if m:
            target = (m.group(1) or m.group(2)).strip()
            return CommandIntent(
                intent_name="resume_routine",
                action_name="resume_routine",
                category=CommandCategory.ROUTINE,
                confidence=1.0,
                params={"routine_id": target},
                risk_level=CommandRiskLevel.LOW,
            )

        m = self._routine_delete_re.match(text)
        if m:
            target = (m.group(1) or m.group(2)).strip()
            return CommandIntent(
                intent_name="delete_routine",
                action_name="delete_routine",
                category=CommandCategory.ROUTINE,
                confidence=1.0,
                params={"routine_id": target},
                risk_level=CommandRiskLevel.MEDIUM,
            )

        m = self._routine_run_now_re.match(text)
        if m:
            target = (m.group(1) or m.group(2)).strip()
            return CommandIntent(
                intent_name="run_routine_now",
                action_name="run_routine_now",
                category=CommandCategory.ROUTINE,
                confidence=1.0,
                params={"routine_id": target},
                risk_level=CommandRiskLevel.MEDIUM,
            )

        m = self._reminder_at_re.match(text)
        if m:
            time_str = m.group(1) if m.group(1) else m.group(4)
            msg = m.group(2) if m.group(2) else m.group(3)
            return CommandIntent(
                intent_name="create_reminder",
                action_name="create_reminder",
                category=CommandCategory.ROUTINE,
                confidence=1.0,
                params={"time": time_str.strip(), "message": msg.strip()},
                risk_level=CommandRiskLevel.LOW,
            )

        # 14.5 WhatsApp Direct Messaging
        for pat in (
            self._whatsapp_send_re1,
            self._whatsapp_send_re2,
            self._whatsapp_send_re3,
            self._whatsapp_send_re4,
            self._whatsapp_send_re5,
            self._whatsapp_tell_re,
            self._whatsapp_message_on_re,
            self._whatsapp_send_direct_re,
            self._whatsapp_colon_re,
        ):
            m = pat.match(text)
            if m:
                contact = m.group(1).strip()
                if contact.lower().endswith(" on whatsapp"):
                    contact = contact[:-12].strip()
                if contact.lower().startswith("contact "):
                    contact = contact[8:].strip()
                elif contact.lower().startswith("to "):
                    contact = contact[3:].strip()
                
                msg = m.group(2).strip()
                if (msg.startswith('"') and msg.endswith('"')) or (msg.startswith("'") and msg.endswith("'")):
                    msg = msg[1:-1].strip()
                return CommandIntent(
                    intent_name="send_whatsapp_message",
                    action_name="send_whatsapp_message",
                    category=CommandCategory.APPLICATION,
                    confidence=1.0,
                    params={"contact": contact, "message": msg},
                    risk_level=CommandRiskLevel.LOW,
                )

        # 15. Application Launch & Close
        m = self._app_open_re.match(text)
        if m:
            target = m.group(1).strip()
            
            # If target has conjunctions/clauses like " and ", " then ", " with ", " to send ", " make msg ", it's a compound intent: pass to AI fallback
            if re.search(r"\b(?:and\s+then|and|then|to\s+send|with\s+message|saying|make\s+msg|send\s+msg|msg|send)\b", target, flags=re.IGNORECASE):
                return self._unknown_intent(text)

            clean_target = re.sub(r"^(?:the|my|a|an)\s+", "", target, flags=re.IGNORECASE).strip()
            clean_target = re.sub(r"\s+(?:app|application|program)$", "", clean_target, flags=re.IGNORECASE).strip()
            effective_target = clean_target or target

            known_sites = {
                "google", "youtube", "github", "gmail", "reddit", "wikipedia",
                "bing", "duckduckgo", "stackoverflow", "chatgpt", "claude", "whatsapp web"
            }
            if (
                effective_target.lower() in known_sites
                or target.lower() in known_sites
                or target.startswith("http://")
                or target.startswith("https://")
                or target.startswith("www.")
            ):
                return CommandIntent(
                    intent_name="open_browser",
                    action_name="open_browser",
                    category=CommandCategory.APPLICATION,
                    confidence=1.0,
                    params={"target": effective_target},
                    risk_level=CommandRiskLevel.LOW,
                )

            return CommandIntent(
                intent_name="open_application",
                action_name="open_application",
                category=CommandCategory.APPLICATION,
                confidence=1.0,
                params={"application": effective_target},
                risk_level=CommandRiskLevel.LOW,
            )

        m = self._app_close_re.match(text)
        if m:
            app_name = m.group(1).strip()
            if re.search(r"\b(?:and\s+then|and|then)\b", app_name, flags=re.IGNORECASE):
                return self._unknown_intent(text)
            clean_app = re.sub(r"^(?:the|my|a|an)\s+", "", app_name, flags=re.IGNORECASE).strip()
            clean_app = re.sub(r"\s+(?:app|application|program)$", "", clean_app, flags=re.IGNORECASE).strip()
            effective_app = clean_app or app_name
            return CommandIntent(
                intent_name="close_application",
                action_name="close_application",
                category=CommandCategory.APPLICATION,
                confidence=1.0,
                params={"application": effective_app},
                risk_level=CommandRiskLevel.MEDIUM,
                requires_confirmation=False,
            )

        return self._unknown_intent(text)

    def _unknown_intent(self, raw_text: str) -> CommandIntent:
        """Fallback for unclassified user utterances."""
        logger.debug("No local intent match found for utterance: '%s'", raw_text)
        return CommandIntent(
            intent_name="unknown",
            action_name="unknown",
            category=CommandCategory.UNKNOWN,
            confidence=0.0,
            params={"raw_text": raw_text},
            risk_level=CommandRiskLevel.SAFE,
        )
