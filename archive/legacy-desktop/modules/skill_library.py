from typing import Any

from .browser_controller import BrowserController


class SkillLibrary:
    def __init__(self, controller: BrowserController) -> None:
        self.controller = controller

    def login(
        self,
        site_name: str,
        url: str,
        username: str,
        password: str,
        username_selector: list[dict[str, str]],
        password_selector: list[dict[str, str]],
        submit_selector: list[dict[str, str]],
    ) -> dict[str, Any]:
        actions = [
            {"name": "fill_username", "type": "fill", "selectors": username_selector, "value": username, "wait": "visible"},
            {"name": "fill_password", "type": "fill", "selectors": password_selector, "value": password, "wait": "visible"},
            {"name": "submit_login", "type": "click", "selectors": submit_selector, "wait": "networkidle"},
        ]
        return self.controller.run_task_loop(site_name=site_name, start_url=url, goal="login", actions=actions)

    def search(
        self,
        site_name: str,
        url: str,
        query: str,
        search_input_selectors: list[dict[str, str]],
        submit_selectors: list[dict[str, str]],
    ) -> dict[str, Any]:
        actions = [
            {"name": "fill_search", "type": "fill", "selectors": search_input_selectors, "value": query, "wait": "visible"},
            {"name": "submit_search", "type": "press", "selectors": submit_selectors, "key": "Enter", "wait": "networkidle"},
        ]
        return self.controller.run_task_loop(site_name=site_name, start_url=url, goal="search", actions=actions)

    def click_button_by_text(self, site_name: str, url: str, button_text: str) -> dict[str, Any]:
        actions = [
            {
                "name": "click_button_by_text",
                "type": "click",
                "selectors": [
                    {"type": "role", "value": f"button::{button_text}"},
                    {"type": "text", "value": button_text},
                ],
                "wait": "networkidle",
            }
        ]
        return self.controller.run_task_loop(site_name=site_name, start_url=url, goal="click button by text", actions=actions)

    def fill_form(self, site_name: str, url: str, fields: list[dict[str, Any]]) -> dict[str, Any]:
        actions: list[dict[str, Any]] = []
        for idx, field in enumerate(fields):
            actions.append(
                {
                    "name": f"fill_form_field_{idx+1}",
                    "type": "fill",
                    "selectors": field.get("selectors", []),
                    "value": field.get("value", ""),
                    "wait": "visible",
                }
            )
        return self.controller.run_task_loop(site_name=site_name, start_url=url, goal="fill form", actions=actions)

    def handle_dropdown(self, site_name: str, url: str, open_selectors: list[dict[str, str]], option_selectors: list[dict[str, str]]) -> dict[str, Any]:
        actions = [
            {"name": "open_dropdown", "type": "click", "selectors": open_selectors, "wait": "visible"},
            {"name": "choose_option", "type": "click", "selectors": option_selectors, "wait": "visible"},
        ]
        return self.controller.run_task_loop(site_name=site_name, start_url=url, goal="handle dropdown", actions=actions)

    def switch_iframe(self, site_name: str, url: str, target_selectors: list[dict[str, str]]) -> dict[str, Any]:
        actions = [{"name": "switch_iframe_target", "type": "click", "selectors": target_selectors, "wait": "visible"}]
        return self.controller.run_task_loop(site_name=site_name, start_url=url, goal="switch iframe", actions=actions)

    def handle_file_download(self, site_name: str, url: str, trigger_selectors: list[dict[str, str]]) -> dict[str, Any]:
        actions = [{"name": "trigger_download", "type": "click", "selectors": trigger_selectors, "wait": "networkidle"}]
        return self.controller.run_task_loop(site_name=site_name, start_url=url, goal="handle file download", actions=actions)

    def handle_popup(self, site_name: str, url: str, dismiss_selectors: list[dict[str, str]]) -> dict[str, Any]:
        actions = [{"name": "dismiss_popup", "type": "click", "selectors": dismiss_selectors, "wait": "visible"}]
        return self.controller.run_task_loop(site_name=site_name, start_url=url, goal="handle popup", actions=actions)

    def paginate_table(self, site_name: str, url: str, next_selectors: list[dict[str, str]]) -> dict[str, Any]:
        actions = [{"name": "paginate_next", "type": "click", "selectors": next_selectors, "wait": "networkidle"}]
        return self.controller.run_task_loop(site_name=site_name, start_url=url, goal="paginate table", actions=actions)
