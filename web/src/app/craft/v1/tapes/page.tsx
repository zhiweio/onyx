"use client";

/**
 * Personal execution-tape entry (/craft/v1/tapes): a dsh-style master-detail
 * browser — the session list on the left, the selected session's trajectory
 * (or replay) on the right, resizable between them. Selection syncs to
 * ?sessionId= so refresh keeps the detail and links carry it. Server-side
 * every read is ownership-scoped (/build/tape).
 */

import { useCallback, useState } from "react";
import { useTranslations } from "next-intl";
import { SvgHistory } from "@opal/icons";
import { SettingsLayouts } from "@opal/layouts";
import TapeListBrowser from "@/components/craft-tape/TapeListBrowser";
import TapeNoSelection from "@/components/craft-tape/TapeNoSelection";
import TapeSessionDetail from "@/components/craft-tape/TapeSessionDetail";
import { useTapeSelection } from "@/components/craft-tape/useTapeSelection";
import type { TapeSessionItem } from "@/lib/craft-tape/types";
import {
  ResizableHandle,
  ResizablePanel,
  ResizablePanelGroup,
} from "@/sections/extend/ui/resizable";

export default function CraftTapesPage() {
  const t = useTranslations("craftTape");
  const { selectedId, select } = useTapeSelection();
  // List rows hydrate the detail header; a deep link opens the detail before
  // the list has (or ever loads) the row, and the header degrades gracefully.
  const [knownSessions, setKnownSessions] = useState<
    Map<string, TapeSessionItem>
  >(new Map());

  const onItemsKnown = useCallback((items: TapeSessionItem[]) => {
    setKnownSessions((current) => {
      const next = new Map(current);
      for (const item of items) next.set(item.session_id, item);
      return next.size === current.size ? current : next;
    });
  }, []);

  const selected = selectedId ? (knownSessions.get(selectedId) ?? null) : null;

  return (
    <SettingsLayouts.Root width="full">
      <SettingsLayouts.Header
        icon={SvgHistory}
        title={t("myPage.title")}
        description={t("myPage.description")}
        divider
      />
      <SettingsLayouts.Body>
        <div
          className="flex h-[calc(100dvh-20rem)] min-h-[28rem]"
          data-testid="my-craft-tapes-page"
        >
          <ResizablePanelGroup orientation="horizontal">
            <ResizablePanel defaultSize="30" minSize="20" className="h-full">
              <TapeListBrowser
                variant="personal"
                selectedId={selectedId}
                onSelect={(session) => select(session.session_id)}
                onItemsKnown={onItemsKnown}
              />
            </ResizablePanel>
            <ResizableHandle />
            <ResizablePanel defaultSize="70" className="h-full">
              {selectedId ? (
                <div className="h-full overflow-y-auto pl-4 pr-1">
                  <TapeSessionDetail
                    key={selectedId}
                    sessionId={selectedId}
                    session={selected}
                    variant="personal"
                    onClose={() => select(null)}
                  />
                </div>
              ) : (
                <TapeNoSelection />
              )}
            </ResizablePanel>
          </ResizablePanelGroup>
        </div>
      </SettingsLayouts.Body>
    </SettingsLayouts.Root>
  );
}
