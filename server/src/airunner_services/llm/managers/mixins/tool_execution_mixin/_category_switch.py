"""Category switch and rebind logic for ToolExecutionMixin."""

from __future__ import annotations


class ToolExecutionCategorySwitchMixin:
    """Prebind, rebind, and handle switch_tool_category calls."""

    def _prebind_for_pending_category_switch(
        self, tool_calls: list[dict],
    ) -> None:
        """Rebind tools early when the batch includes switch_tool_category.

        If the model emits ``switch_tool_category`` and a target-category
        tool in the **same** ``AIMessage`` batch, :class:`ToolNode` would
        reject the target tool because ``self._tools`` still reflects the
        pre-switch category.  This method pre-scans for a pending switch,
        validates it via the actual tool function, and rebinds before
        :class:`ToolNode` is constructed.

        ``switch_tool_category`` is kept in the tool set (via
        ``keep_switch=True``) so that :class:`ToolNode` can execute it
        and record its :class:`ToolMessage` in the conversation.

        Args:
            tool_calls: Tool-call dicts from the current AIMessage.
        """
        from airunner_services.llm.core.tool_registry import ToolCategory
        from airunner_services.llm.tools.orchestration_tools import (
            _enabled_category_descriptions,
        )

        enabled = _enabled_category_descriptions()

        for tc in tool_calls:
            if tc.get("name") != "switch_tool_category":
                continue
            args = tc.get("args", {})
            category_name = (args.get("category", "") or "").strip().lower()
            if not category_name:
                continue

            if category_name not in enabled:
                continue

            try:
                target = ToolCategory(category_name)
            except ValueError:
                continue

            self._rebind_for_category(target, keep_switch=True)
            tc_id = tc.get("id")
            if tc_id:
                self._prebound_switch_ids.add(tc_id)
            return

    def _handle_category_switch(
        self,
        tool_calls: list[dict],
        result_state: dict,
    ) -> None:
        """Rebind tools when switch_tool_category succeeds.

        Parses ToolMessage results from the current tool-execution cycle
        and, if switch_tool_category completed successfully, replaces
        the bound tool set with tools from the target category (plus the
        always-available orchestration tools) for the next model turn.

        Args:
            tool_calls: Tool-call dicts from the current AIMessage.
            result_state: Workflow state after ToolNode execution.
        """
        import json as _json

        from langchain_core.messages import ToolMessage

        from airunner_services.llm.core.tool_registry \
            import ToolCategory

        # Find switch_tool_category calls and their results.
        # Skip calls already handled by _prebind_for_pending_category_switch
        # to avoid a duplicate unbind/rebind cycle.
        for tc in tool_calls:
            if tc.get("name") != "switch_tool_category":
                continue
            if tc.get("id") in self._prebound_switch_ids:
                # Prebind already handled the category switch.  Skip the
                # redundant get_tools_by_categories refetch, but still
                # strip switch_tool_category from self._tools — it just
                # did its job and calling it again is pointless.
                # Strip switch_tool_category using list.remove()
                # to preserve list identity for prompt-cache stability.
                switch_tool = None
                for t in self._tools:
                    if getattr(t, "name", None) == "switch_tool_category":
                        switch_tool = t
                        break
                if switch_tool is not None:
                    self._tools.remove(switch_tool)
                    self._unbind_tools_from_model()
                    if self._tools:
                        self._bind_tools_to_model()
                return
            tc_id = tc.get("id")
            if not tc_id:
                continue
            for msg in result_state.get("messages", []):
                if (
                    isinstance(msg, ToolMessage)
                    and getattr(msg, "tool_call_id", None) == tc_id
                ):
                    try:
                        parsed = _json.loads(str(msg.content))
                    except (_json.JSONDecodeError, TypeError):
                        continue
                    if not parsed.get("success"):
                        continue
                    category_name = parsed.get("category", "")
                    if not category_name:
                        continue
                    try:
                        target = ToolCategory(category_name)
                    except ValueError:
                        continue
                    self._rebind_for_category(target)
                    return

    def _rebind_for_category(
        self, category, keep_switch: bool = False,
    ) -> None:
        """Append category tools to the existing bound set (append-only).

        Preserves always-available orchestration tools (list_tool_categories,
        switch_tool_category) alongside the category-specific tools.

        Uses append-only semantics to keep the tools array prefix-stable
        for Anthropic prompt caching.  New tools are appended to the
        existing cumulative set; duplicates are skipped.  The model is
        guided to use the right category via prompt instructions, not by
        shrinking the bound schema array.

        Args:
            category: The ToolCategory to switch to.
            keep_switch: If True, retain switch_tool_category in the bound
                tools.  Used by early prebind so switch_tool_category can
                still execute through ToolNode and produce its ToolMessage.
        """
        from airunner_services.llm.core.tool_registry import ToolCategory

        if not self._tool_manager:
            self.logger.warning(
                "Cannot rebind for category %s — no tool_manager",
                category.value,
            )
            return
        category_tools = self._tool_manager.get_tools_by_categories(
            [category],
            include_deferred=True,
        )
        orch_tools = self._tool_manager.get_tools_by_categories(
            [ToolCategory.ORCHESTRATION],
            include_deferred=True,
        )

        # Build the deduplicated list of tools to add.
        to_add: list = list(category_tools)
        new_names = {
            getattr(t, "name", getattr(t, "__name__", None))
            for t in to_add
        }
        for ot in orch_tools:
            name = getattr(ot, "name", getattr(ot, "__name__", None))
            # Strip switch_tool_category on success — it just did its
            # job and calling it again in the same turn is pointless.
            # When keep_switch is True (early prebind), retain it so
            # ToolNode can execute it and record its ToolMessage.
            if name == "switch_tool_category" and not keep_switch:
                continue
            if name not in new_names:
                to_add.append(ot)
                new_names.add(name)

        # Append-only: add tools not already in self._tools.
        existing_names = {
            getattr(t, "name", getattr(t, "__name__", None))
            for t in self._tools
        }
        added = 0
        for tool in to_add:
            name = getattr(tool, "name", getattr(tool, "__name__", None))
            if name and name not in existing_names:
                self._tools.append(tool)
                existing_names.add(name)
                added += 1

        # When keep_switch is False, strip switch_tool_category via
        # list.remove() — it just executed successfully and calling
        # it again mid-turn is pointless.  Mirrors the logic in
        # _handle_category_switch's prebound path.  Uses remove()
        # (not list rebuild) to preserve cache-prefix stability.
        if not keep_switch:
            switch_tool = None
            for t in self._tools:
                if getattr(t, "name", None) == "switch_tool_category":
                    switch_tool = t
                    break
            if switch_tool is not None:
                self._tools.remove(switch_tool)

        self.logger.info(
            "Category switch: appended %d new tools from '%s' "
            "(+ orchestration, total: %d tools)",
            added,
            category.value,
            len(self._tools),
        )
        self._unbind_tools_from_model()
        if self._tools:
            self._bind_tools_to_model()
