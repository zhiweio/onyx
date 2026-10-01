"use client";

import useSWR, { mutate } from "swr";
import { errorHandlingFetcher } from "@/lib/fetcher";
import { SWR_KEYS } from "@/lib/swr-keys";
import { UserGroup } from "@/lib/types";

/**
 * Fetches all user groups in the organization.
 *
 * Returns group information including group members, curators, and associated resources.
 * Use this for displaying group lists in sharing dialogs, admin panels, or permission
 * management interfaces.
 *
 * @returns Object containing:
 *   - data: Array of UserGroup objects, or undefined while loading
 *   - isLoading: Boolean indicating if data is being fetched
 *   - error: Any error that occurred during fetch
 *   - refreshGroups: Function to manually revalidate the data
 *
 * @param includeDefault Include the seeded Admin and Basic groups, which group
 *   management hides. The service-account forms opt in to grant a key any access.
 */
export default function useGroups(includeDefault = false) {
  const url = includeDefault
    ? SWR_KEYS.adminUserGroupsWithDefault
    : SWR_KEYS.adminUserGroups;

  const { data, error, isLoading } = useSWR<UserGroup[]>(
    url,
    errorHandlingFetcher
  );

  const refreshGroups = () => mutate(url);

  return {
    data,
    isLoading,
    error,
    refreshGroups,
  };
}
