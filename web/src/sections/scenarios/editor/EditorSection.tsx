"use client";

import type { ReactNode } from "react";
import { Content, ContentAction } from "@opal/layouts";
import { Section } from "@/layouts/general-layouts";

interface EditorSectionProps {
  title: string;
  description?: string;
  action?: ReactNode;
  children: ReactNode;
}

export default function EditorSection({
  title,
  description,
  action,
  children,
}: EditorSectionProps) {
  return (
    <Section gap={3} alignItems="stretch" height="auto">
      {action ? (
        <ContentAction
          title={title}
          description={description}
          sizePreset="main-content"
          variant="section"
          rightChildren={action}
        />
      ) : (
        <Content
          title={title}
          description={description}
          sizePreset="main-content"
          variant="section"
        />
      )}
      {children}
    </Section>
  );
}
