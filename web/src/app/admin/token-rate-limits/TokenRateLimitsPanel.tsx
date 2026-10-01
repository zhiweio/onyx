"use client";

import { useTranslations } from "next-intl";
import { Button, Tabs, Text } from "@opal/components";
import { toast } from "@opal/layouts";
import { useState } from "react";
import { mutate } from "swr";
import { SWR_KEYS } from "@/lib/swr-keys";
import { Section } from "@/layouts/general-layouts";
import { SvgPlusCircle } from "@opal/icons";
import {
  insertGlobalTokenRateLimit,
  insertGroupTokenRateLimit,
  insertUserTokenRateLimit,
} from "./lib";
import { Scope, TokenRateLimit } from "./types";
import { GenericTokenRateLimitTable } from "./TokenRateLimitTables";
import CreateRateLimitModal from "./CreateRateLimitModal";

const GLOBAL_TOKEN_FETCH_URL = SWR_KEYS.globalTokenRateLimits;
const USER_TOKEN_FETCH_URL = SWR_KEYS.userTokenRateLimits;
const USER_GROUP_FETCH_URL = SWR_KEYS.userGroupTokenRateLimits;

type PanelTab = "global" | "users" | "groups";

async function createTokenRateLimit(
  targetScope: Scope,
  periodHours: number,
  tokenBudget: number | null,
  costBudgetCents: number | null,
  groupId: number
): Promise<void> {
  const tokenRateLimitArgs = {
    enabled: true,
    token_budget: tokenBudget,
    period_hours: periodHours,
    cost_budget_cents: costBudgetCents,
  };

  if (targetScope === Scope.GLOBAL) {
    await insertGlobalTokenRateLimit(tokenRateLimitArgs);
  } else if (targetScope === Scope.USER) {
    await insertUserTokenRateLimit(tokenRateLimitArgs);
  } else if (targetScope === Scope.USER_GROUP) {
    await insertGroupTokenRateLimit(tokenRateLimitArgs, groupId);
  } else {
    throw new Error(`Invalid target scope: ${targetScope}`);
  }
}

interface TokenRateLimitsPanelProps {
  embedded?: boolean;
}

export default function TokenRateLimitsPanel({
  embedded = false,
}: TokenRateLimitsPanelProps) {
  const t = useTranslations("admin.tokenRateLimits");
  const [tab, setTab] = useState<PanelTab>("global");
  const [modalIsOpen, setModalIsOpen] = useState(false);

  function updateTable(targetScope: Scope) {
    if (targetScope === Scope.GLOBAL) {
      mutate(GLOBAL_TOKEN_FETCH_URL);
      setTab("global");
    } else if (targetScope === Scope.USER) {
      mutate(USER_TOKEN_FETCH_URL);
      setTab("users");
    } else if (targetScope === Scope.USER_GROUP) {
      mutate(USER_GROUP_FETCH_URL);
      setTab("groups");
    }
  }

  async function handleSubmit(
    targetScope: Scope,
    periodHours: number,
    tokenBudget: number | null,
    costBudgetCents: number | null,
    groupId: number = -1
  ): Promise<void> {
    try {
      await createTokenRateLimit(
        targetScope,
        periodHours,
        tokenBudget,
        costBudgetCents,
        groupId
      );
      setModalIsOpen(false);
      toast.success(t("panel.created.message"));
      updateTable(targetScope);
    } catch (error) {
      console.error("Failed to create spending limit:", error);
      toast.error(
        error instanceof Error ? error.message : t("panel.createFailed.error")
      );
    }
  }

  return (
    <Section alignItems="stretch" justifyContent="start" height="auto">
      {embedded ? (
        <Section gap={1} alignItems="start" justifyContent="start">
          <Text font="heading-h3">{t("panel.embedded.title")}</Text>
          <Text font="secondary-body" color="text-03">
            {t("panel.embedded.description")}
          </Text>
        </Section>
      ) : (
        <>
          <Text as="p">{t("panel.intro.description")}</Text>
          <ul className="list-disc ms-4">
            <li>
              <Text as="p">{t("panel.intro.workspaceLimit")}</Text>
            </li>
            <li>
              <Text as="p">{t("panel.intro.userLimit")}</Text>
            </li>
            <li>
              <Text as="p">{t("panel.intro.groupLimit")}</Text>
            </li>
            <li>
              <Text as="p">{t("panel.intro.toggleLimit")}</Text>
            </li>
          </ul>
        </>
      )}

      <Button
        icon={SvgPlusCircle}
        prominence="secondary"
        onClick={() => setModalIsOpen(true)}
      >
        {t("panel.create.label")}
      </Button>

      <Tabs value={tab} onValueChange={(value) => setTab(value as PanelTab)}>
          <Tabs.List>
            <Tabs.Trigger value="global">
              {t("panel.tabs.global.name")}
            </Tabs.Trigger>
            <Tabs.Trigger value="users">
              {t("panel.tabs.users.name")}
            </Tabs.Trigger>
            <Tabs.Trigger value="groups">
              {t("panel.tabs.groups.name")}
            </Tabs.Trigger>
          </Tabs.List>
          <Tabs.Content value="global">
            <GenericTokenRateLimitTable
              fetchUrl={GLOBAL_TOKEN_FETCH_URL}
              description={t("panel.global.description")}
            />
          </Tabs.Content>
          <Tabs.Content value="users">
            <GenericTokenRateLimitTable
              fetchUrl={USER_TOKEN_FETCH_URL}
              description={t("panel.user.description")}
            />
          </Tabs.Content>
          <Tabs.Content value="groups">
            <GenericTokenRateLimitTable
              fetchUrl={USER_GROUP_FETCH_URL}
              description={t("panel.userGroup.description")}
              responseMapper={(data: Record<string, TokenRateLimit[]>) =>
                Object.entries(data).flatMap(([groupName, elements]) =>
                  elements.map((element) => ({
                    ...element,
                    group_name: groupName,
                  }))
                )
              }
            />
          </Tabs.Content>
        </Tabs>

      <CreateRateLimitModal
        isOpen={modalIsOpen}
        setIsOpen={() => setModalIsOpen(false)}
        onSubmit={handleSubmit}
      />
    </Section>
  );
}
