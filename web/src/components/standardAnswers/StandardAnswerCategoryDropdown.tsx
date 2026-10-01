import { FC } from "react";
import { useTranslations } from "next-intl";
import { Label } from "@/components/Field";
import InputComboBox from "@/refresh-components/inputs/InputComboBox/InputComboBox";
import Chip from "@/refresh-components/Chip";
import { StandardAnswerCategory } from "@/lib/types";
import { LoadingAnimation } from "../Loading";

interface StandardAnswerCategoryDropdownFieldProps {
  allCategories: StandardAnswerCategory[] | null;
  categories: StandardAnswerCategory[];
  setCategories: (categories: StandardAnswerCategory[]) => void;
}

export const StandardAnswerCategoryDropdownField: FC<
  StandardAnswerCategoryDropdownFieldProps
> = ({ allCategories, categories, setCategories }) => {
  const t = useTranslations("admin.standardAnswers.categoryDropdown");

  if (allCategories == null) {
    return <LoadingAnimation />;
  }

  const selectedIds = new Set(categories.map((category) => category.id));

  return (
    <div>
      <Label>{t("categories.label")}</Label>
      <div className="w-64 flex flex-col gap-2">
        <InputComboBox
          placeholder={t("search.placeholder")}
          value=""
          onChange={() => {}}
          onValueChange={(value) => {
            const category = allCategories.find(
              (candidate) => candidate.id.toString() === value
            );
            if (category && !selectedIds.has(category.id)) {
              setCategories([...categories, category]);
            }
          }}
          options={allCategories
            .filter((category) => !selectedIds.has(category.id))
            .map((category) => ({
              label: category.name,
              value: category.id.toString(),
            }))}
          strict
          searchIcon
        />

        {categories.length > 0 && (
          <div className="flex flex-wrap gap-1.5">
            {categories.map((category) => (
              <Chip
                key={category.id}
                onRemove={() =>
                  setCategories(categories.filter((c) => c.id !== category.id))
                }
              >
                {category.name}
              </Chip>
            ))}
          </div>
        )}
      </div>
    </div>
  );
};
