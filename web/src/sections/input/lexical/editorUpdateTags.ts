/** Update tags used across the Lexical prompt-input kernel. */

/** Editor was rewritten programmatically (draft restore, chip insertion). */
export const PROGRAMMATIC_UPDATE_TAG = "onyx-programmatic-update";

/** Editor was filled by prompt-history navigation (↑/↓). Trigger menus must
 * not reopen for these updates — a restored `/foo` history entry is not the
 * user typing a slash query. */
export const HISTORY_NAVIGATION_UPDATE_TAG = "onyx-history-navigation";
