import { useState } from "react";
import { render, screen, setupUser } from "@tests/setup/test-utils";
import type { SystemCatalogCategory } from "@/lib/system-catalog/types";
import CatalogListingFields, {
  type CatalogListingFieldCopy,
} from "@/sections/catalog/CatalogListingFields";

const copy: CatalogListingFieldCopy = {
  name: "Name",
  namePlaceholder: "Display name",
  description: "Description",
  descriptionPlaceholder: "What this listing offers",
  category: "Category",
  tags: "Tags",
  tagsPlaceholder: "Add a tag and press Enter",
  tagsHint: "At most 20 tags, 32 characters each. Tags are stored in lowercase.",
  count: (used, max) => `${used}/${max}`,
  categoryLabel: (category) => category,
};

function ListingHarness() {
  const [name, setName] = useState("Chart generation");
  const [description, setDescription] = useState("Generate charts from JSON.");
  const [category, setCategory] = useState<SystemCatalogCategory>("GRAPHIC");
  const [tags, setTags] = useState<string[]>(["chart"]);
  return (
    <CatalogListingFields
      name={name}
      description={description}
      category={category}
      tags={tags}
      nameMax={64}
      copy={copy}
      onNameChange={setName}
      onDescriptionChange={setDescription}
      onCategoryChange={setCategory}
      onTagsChange={setTags}
    />
  );
}

describe("CatalogListingFields", () => {
  it("keeps listing fields full width and uses an Opal category select", () => {
    render(<ListingHarness />);

    const description = document.getElementById("catalog-listing-description");
    expect(description).toBeInstanceOf(HTMLTextAreaElement);
    expect(description?.closest(".w-full")).not.toBeNull();
    expect(screen.getByRole("combobox")).toHaveTextContent("GRAPHIC");
  });

  it("adds lowercase tags on Enter and comma, and can remove them", async () => {
    const user = setupUser();
    render(<ListingHarness />);

    const tagInput = screen.getByPlaceholderText("Add a tag and press Enter");
    await user.type(tagInput, "Kimi{Enter}");
    expect(screen.getByText("kimi")).toBeInTheDocument();

    await user.type(tagInput, "Route,");
    expect(screen.getByText("route")).toBeInTheDocument();

    await user.type(tagInput, "chart{Enter}");
    expect(screen.getAllByText("chart")).toHaveLength(1);

    const removeButtons = screen.getAllByRole("button", { name: /remove/i });
    await user.click(removeButtons[0]!);
    expect(screen.queryByText("chart")).not.toBeInTheDocument();
  });
});
