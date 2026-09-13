"use client";

import { useTranslations } from "next-intl";
import { Modal } from "@opal/components";
import { SvgFolder } from "@opal/icons";
import { Button, InputTypeIn } from "@opal/components";
import { Section } from "@/layouts/general-layouts";
import { useUserLibrary } from "@/app/craft/hooks/useUserLibrary";
import {
  UserLibraryActions,
  UserLibraryManager,
} from "@/app/craft/components/UserLibraryManager";

interface UserLibraryModalProps {
  open: boolean;
  onClose: () => void;
  onChanges?: () => void;
}

export default function UserLibraryModal({
  open,
  onClose,
  onChanges,
}: UserLibraryModalProps) {
  const t = useTranslations("craft.userLibrary");
  const library = useUserLibrary({ enabled: open, onChanges });

  return (
    <Modal open={open} onOpenChange={(isOpen) => !isOpen && onClose()}>
      <Modal.Content
        width="sm"
        height="fit"
        preventAccidentalClose={false}
        onEscapeKeyDown={(event) => {
          if (!library.isCreatingFolder) return;
          event.preventDefault();
          library.cancelCreateFolder();
        }}
      >
        <Modal.Header
          icon={SvgFolder}
          title={t("modal.title")}
          description={t("modal.description")}
          onClose={onClose}
        >
          <Section flexDirection="row" gap={2}>
            <InputTypeIn
              placeholder={t("search.placeholder")}
              value={library.searchQuery}
              onChange={(e) => library.setSearchQuery(e.target.value)}
              searchIcon
              autoComplete="off"
            />
            <UserLibraryActions library={library} />
          </Section>
        </Modal.Header>
        <Modal.Body>
          <UserLibraryManager library={library} variant="modal" />
        </Modal.Body>
        <Modal.Footer>
          <Button prominence="secondary" onClick={onClose}>
            {t("modal.doneButton")}
          </Button>
        </Modal.Footer>
      </Modal.Content>
    </Modal>
  );
}
