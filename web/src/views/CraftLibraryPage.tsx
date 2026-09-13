"use client";

import { useTranslations } from "next-intl";
import { InputTypeIn } from "@opal/components";
import { SettingsLayouts } from "@opal/layouts";
import { SvgFolderOpen } from "@opal/icons";
import TextSeparator from "@/refresh-components/TextSeparator";
import { useUserLibrary } from "@/app/craft/hooks/useUserLibrary";
import {
  UserLibraryActions,
  UserLibraryManager,
} from "@/app/craft/components/UserLibraryManager";

export default function CraftLibraryPage() {
  const t = useTranslations("craft.userLibrary");
  const library = useUserLibrary();

  return (
    <SettingsLayouts.Root
      width="lg"
      data-testid="CraftLibraryPage/container"
    >
      <SettingsLayouts.Header
        icon={SvgFolderOpen}
        title={t("page.title.text")}
        description={t("page.description.text")}
        rightChildren={
          <div className="flex items-center gap-2">
            <UserLibraryActions library={library} />
          </div>
        }
      >
        <InputTypeIn
          placeholder={t("search.placeholder")}
          value={library.searchQuery}
          onChange={(event) => library.setSearchQuery(event.target.value)}
          searchIcon
          autoComplete="off"
        />
      </SettingsLayouts.Header>

      <SettingsLayouts.Body>
        <UserLibraryManager library={library} variant="page" />
        {!library.isLoading && !library.error && !library.isEmpty && (
          <TextSeparator
            text={t("page.count.label", { count: library.fileCount })}
          />
        )}
      </SettingsLayouts.Body>
    </SettingsLayouts.Root>
  );
}
