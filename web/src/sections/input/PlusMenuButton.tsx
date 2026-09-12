"use client";

import { useCallback, useMemo, useState } from "react";
import { useTranslations } from "next-intl";
import { useFocusOnMount } from "@opal/hooks";
import {
  Button,
  InputTypeIn,
  LineItemButton,
  Popover,
  PopoverMenu,
  Switch,
  Text,
} from "@opal/components";
import {
  SvgChevronLeft,
  SvgChevronRight,
  SvgExternalLink,
  SvgPlus,
} from "@opal/icons";
import type { IconFunctionComponent } from "@opal/types";

export interface PlusMenuPanelRow {
  key: string;
  label: string;
  icon?: IconFunctionComponent;
  description?: string;
  checked: boolean;
  onCheckedChange: (checked: boolean) => void;
  onSelect?: () => void;
}

export interface PlusMenuPanel {
  searchPlaceholder: string;
  manageLabel?: string;
  manageHref?: string;
  manageTarget?: string;
  onManage?: () => void;
  emptyLabel?: string;
  rows: PlusMenuPanelRow[];
}

/** A direct-action row (`onSelect`) or a drill-in list (`panel`). */
export interface PlusMenuItem {
  key: string;
  label: string;
  icon: IconFunctionComponent;
  onSelect?: () => void;
  panel?: PlusMenuPanel;
}

export interface PlusMenuButtonProps {
  /** Menu rows. A `null` entry is skipped. */
  items: Array<PlusMenuItem | null>;
  disabled?: boolean;
  tooltip?: string;
  ariaLabel?: string;
}

function PanelView({
  panel,
  onBack,
  onManage,
}: {
  panel: PlusMenuPanel;
  onBack: () => void;
  onManage: () => void;
}) {
  const t = useTranslations("actions");
  const [searchTerm, setSearchTerm] = useState("");
  const focusOnMount = useFocusOnMount<HTMLInputElement>();
  const filteredRows = useMemo(() => {
    if (!searchTerm) return panel.rows;
    const searchLower = searchTerm.toLowerCase();
    return panel.rows.filter(
      (row) =>
        row.label.toLowerCase().includes(searchLower) ||
        (row.description?.toLowerCase().includes(searchLower) ?? false)
    );
  }, [panel.rows, searchTerm]);
  const showManage = Boolean(
    panel.manageLabel && (panel.manageHref || panel.onManage)
  );

  return (
    <PopoverMenu>
      {[
        <div className="flex items-center gap-1" key="header">
          <Button
            icon={SvgChevronLeft}
            prominence="tertiary"
            size="sm"
            aria-label={t("switchList.back.ariaLabel")}
            onClick={() => {
              setSearchTerm("");
              onBack();
            }}
          />
          <div className="min-w-0 flex-1">
            <InputTypeIn
              variant="internal"
              searchIcon
              placeholder={panel.searchPlaceholder}
              value={searchTerm}
              onChange={(event) => setSearchTerm(event.target.value)}
              ref={focusOnMount}
            />
          </div>
          {showManage ? (
            <Button
              href={panel.manageHref}
              target={panel.manageTarget}
              prominence="tertiary"
              size="sm"
              rightIcon={panel.manageHref ? SvgExternalLink : undefined}
              onClick={panel.manageHref ? undefined : onManage}
            >
              {panel.manageLabel ?? ""}
            </Button>
          ) : null}
        </div>,
        ...(filteredRows.length === 0
          ? [
              <Text
                key="empty"
                font="secondary-body"
                color="text-03"
                className="px-2 py-2"
              >
                {panel.emptyLabel ?? ""}
              </Text>,
            ]
          : filteredRows.map((row) => (
              <LineItemButton
                key={row.key}
                title={row.label}
                description={row.description}
                icon={row.icon}
                sizePreset="main-ui"
                variant="section"
                rounding={2}
                onClick={() => {
                  if (row.onSelect) {
                    row.onSelect();
                    return;
                  }
                  row.onCheckedChange(!row.checked);
                }}
                rightChildren={
                  <span
                    onClick={(event) => event.stopPropagation()}
                    onPointerDown={(event) => event.stopPropagation()}
                  >
                    <Switch
                      checked={row.checked}
                      aria-label={t("switchList.toggle.ariaLabel", {
                        name: row.label,
                      })}
                      onCheckedChange={row.onCheckedChange}
                    />
                  </span>
                }
              />
            ))),
      ]}
    </PopoverMenu>
  );
}

export function PlusMenuButton({
  items,
  disabled = false,
  tooltip,
  ariaLabel,
}: PlusMenuButtonProps) {
  const t = useTranslations("chat.input");
  const [open, setOpen] = useState(false);
  const [panelKey, setPanelKey] = useState<string | null>(null);

  const close = useCallback(() => {
    setOpen(false);
    setPanelKey(null);
  }, []);

  const handleOpenChange = (next: boolean) => {
    if (!next) {
      close();
      return;
    }
    setOpen(true);
  };

  const visibleItems = items.filter(
    (item): item is PlusMenuItem => item != null
  );
  const activePanel = visibleItems.find((item) => item.key === panelKey)?.panel;

  const primaryView = (
    <PopoverMenu>
      {visibleItems.map((item) => (
        <LineItemButton
          key={item.key}
          icon={item.icon}
          title={item.label}
          sizePreset="main-ui"
          variant="section"
          rounding={2}
          onClick={() => {
            if (item.panel) {
              setPanelKey(item.key);
              return;
            }
            item.onSelect?.();
            close();
          }}
          rightChildren={
            item.panel ? (
              <span
                aria-hidden="true"
                className="pointer-events-none flex size-6 shrink-0 items-center justify-center"
              >
                <SvgChevronRight className="size-4 stroke-text-03" />
              </span>
            ) : undefined
          }
        />
      ))}
    </PopoverMenu>
  );

  return (
    <Popover open={open} onOpenChange={handleOpenChange}>
      <Popover.Trigger asChild>
        <Button
          icon={SvgPlus}
          prominence="tertiary"
          disabled={disabled}
          tooltip={tooltip ?? t("plusMenuButton.trigger.tooltip")}
          aria-label={ariaLabel ?? t("plusMenuButton.trigger.ariaLabel")}
        />
      </Popover.Trigger>

      <Popover.Content
        side="bottom"
        align="start"
        width="lg"
        onCloseAutoFocus={(event) => event.preventDefault()}
      >
        <div data-testid="craft-plus-menu">
          {activePanel ? (
            <PanelView
              panel={activePanel}
              onBack={() => setPanelKey(null)}
              onManage={() => {
                activePanel.onManage?.();
                close();
              }}
            />
          ) : (
            primaryView
          )}
        </div>
      </Popover.Content>
    </Popover>
  );
}

export default PlusMenuButton;
