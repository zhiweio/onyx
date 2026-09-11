"use client";

import { Pagination } from "@opal/components";
import { BROWSE_PAGE_SIZE, pageCount } from "@/lib/browse/page";

interface BrowsePaginationProps {
  page: number;
  totalItems: number;
  onPageChange: (page: number) => void;
  units: string;
}

export default function BrowsePagination({
  page,
  totalItems,
  onPageChange,
  units,
}: BrowsePaginationProps) {
  const totalPages = pageCount(totalItems);
  if (totalItems <= BROWSE_PAGE_SIZE) {
    return null;
  }

  return (
    <div
      className="flex w-full justify-center pt-2"
      data-testid="BrowsePagination/container"
    >
      <Pagination
        variant="count"
        currentPage={page}
        totalPages={totalPages}
        pageSize={BROWSE_PAGE_SIZE}
        totalItems={totalItems}
        onChange={onPageChange}
        size="sm"
        units={units}
      />
    </div>
  );
}
