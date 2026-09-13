"use client";

import {
  createContext,
  useContext,
  useState,
  useCallback,
  useMemo,
  useRef,
  useEffect,
  type ReactNode,
} from "react";
import { useTranslations } from "next-intl";
import {
  uploadFile as uploadFileApi,
  deleteFile as deleteFileApi,
} from "@/app/craft/services/apiServices";
import { useBuildSessionStore } from "@/app/craft/hooks/useBuildSessionStore";

/**
 * Upload File Status - tracks the state of files being uploaded
 */
export enum UploadFileStatus {
  /** File is currently being uploaded to the sandbox */
  UPLOADING = "UPLOADING",
  /** File is being processed after upload */
  PROCESSING = "PROCESSING",
  /** File has been successfully uploaded and has a path */
  COMPLETED = "COMPLETED",
  /** File upload failed */
  FAILED = "FAILED",
  /** File is waiting for a session to be created before uploading */
  PENDING = "PENDING",
}

/**
 * Build File - represents a file attached to a build session
 */
export interface BuildFile {
  id: string;
  name: string;
  status: UploadFileStatus;
  file_type: string;
  size: number;
  created_at: string;
  // Original File object for upload
  file?: File;
  // Path in sandbox after upload (e.g., "attachments/doc.pdf")
  path?: string;
  // Error message if upload failed
  error?: string;
}

// Helper to generate unique temp IDs
const generateTempId = () => {
  try {
    return `temp_${crypto.randomUUID()}`;
  } catch {
    return `temp_${Date.now()}_${Math.random().toString(36).slice(2, 11)}`;
  }
};

// =============================================================================
// File Validation (matches backend: build/configs.py and build/utils.py)
// =============================================================================

/** Maximum individual file size - matches BUILD_MAX_UPLOAD_FILE_SIZE_MB (50MB) */
const MAX_FILE_SIZE_BYTES = 50 * 1024 * 1024;

/** Maximum total attachment size per session - matches BUILD_MAX_TOTAL_UPLOAD_SIZE_MB (200MB) */
const MAX_TOTAL_SIZE_BYTES = 200 * 1024 * 1024;

/** Maximum files per session - matches BUILD_MAX_UPLOAD_FILES_PER_SESSION */
const MAX_FILES_PER_SESSION = 20;

/** Format bytes to human-readable string */
function formatBytes(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}

/** Validation result for a single file */
interface FileValidationResult {
  valid: boolean;
  error?: string;
}

/** Translator bound to the craft.uploadFiles namespace */
type UploadTranslate = ReturnType<typeof useTranslations<"craft.uploadFiles">>;

/** Validate a single file before upload */
function validateFile(file: File, t: UploadTranslate): FileValidationResult {
  // Check file size. Extension/type are intentionally not restricted - uploaded
  // files only run inside the isolated sandbox, which is the security boundary.
  if (file.size > MAX_FILE_SIZE_BYTES) {
    return {
      valid: false,
      error: t("errors.fileTooLarge", {
        size: formatBytes(file.size),
        max: formatBytes(MAX_FILE_SIZE_BYTES),
      }),
    };
  }

  return { valid: true };
}

/** Validate total files and size constraints */
function validateBatch(
  newFiles: File[],
  existingFiles: BuildFile[],
  t: UploadTranslate
): FileValidationResult {
  const totalCount = existingFiles.length + newFiles.length;
  if (totalCount > MAX_FILES_PER_SESSION) {
    return {
      valid: false,
      error: t("errors.tooManyFiles", { max: MAX_FILES_PER_SESSION }),
    };
  }

  const existingSize = existingFiles.reduce((sum, f) => sum + f.size, 0);
  const newSize = newFiles.reduce((sum, f) => sum + f.size, 0);
  const totalSize = existingSize + newSize;

  if (totalSize > MAX_TOTAL_SIZE_BYTES) {
    return {
      valid: false,
      error: t("errors.totalSizeExceeded", {
        max: formatBytes(MAX_TOTAL_SIZE_BYTES),
      }),
    };
  }

  return { valid: true };
}

/** Create a failed BuildFile for validation errors */
function createFailedFile(file: File, error: string): BuildFile {
  return {
    id: generateTempId(),
    name: file.name,
    status: UploadFileStatus.FAILED,
    file_type: file.type,
    size: file.size,
    created_at: new Date().toISOString(),
    error,
  };
}

// Create optimistic file from File object
const createOptimisticFile = (file: File): BuildFile => {
  const tempId = generateTempId();
  return {
    id: tempId,
    name: file.name,
    status: UploadFileStatus.UPLOADING,
    file_type: file.type,
    size: file.size,
    created_at: new Date().toISOString(),
    file,
  };
};

/**
 * Error types for better error handling
 */
export enum UploadErrorType {
  NETWORK = "NETWORK",
  AUTH = "AUTH",
  NOT_FOUND = "NOT_FOUND",
  SERVER = "SERVER",
  UNKNOWN = "UNKNOWN",
}

function classifyError(
  error: unknown,
  t: UploadTranslate
): {
  type: UploadErrorType;
  message: string;
} {
  if (error instanceof Error) {
    const message = error.message.toLowerCase();
    if (message.includes("401") || message.includes("unauthorized")) {
      return {
        type: UploadErrorType.AUTH,
        message: t("errors.sessionExpired"),
      };
    }
    if (message.includes("404") || message.includes("not found")) {
      return {
        type: UploadErrorType.NOT_FOUND,
        message: t("errors.notFound"),
      };
    }
    if (message.includes("500") || message.includes("server")) {
      return { type: UploadErrorType.SERVER, message: t("errors.server") };
    }
    if (message.includes("network") || message.includes("fetch")) {
      return { type: UploadErrorType.NETWORK, message: t("errors.network") };
    }
    return { type: UploadErrorType.UNKNOWN, message: error.message };
  }
  return { type: UploadErrorType.UNKNOWN, message: t("errors.uploadFailed") };
}

/**
 * UploadFilesContext - Centralized file upload state management
 *
 * This context manages:
 * - Draft file chips on the input bar (next message only)
 * - Active session binding (which session uploads go to)
 * - Automatic upload of pending files when a session becomes available
 * - File upload, removal, and clearing operations
 *
 * Sandbox `attachments/` is not a source of truth for the input bar. Sent
 * files stay in the sandbox for the agent; they must not reappear as chips.
 *
 * Components should:
 * - Call `setActiveSession(sessionId)` when session changes
 * - Call `uploadFiles(files)` to attach files (uses active session internally)
 * - Call `removeFile(fileId)` to remove files (uses active session internally)
 * - Read `currentMessageFiles` to display attached files
 */
interface UploadFilesContextValue {
  // Current message files (attached to the input bar)
  currentMessageFiles: BuildFile[];

  // Active session ID (set by parent components)
  activeSessionId: string | null;

  /**
   * Set the active session ID. This triggers:
   * - Dropping completed draft chips when switching to a different session
   * - Auto-uploading any pending files
   *
   * Call this when:
   * - Session ID changes in URL
   * - Pre-provisioned session becomes available
   */
  setActiveSession: (sessionId: string | null) => void;

  /**
   * Upload files to the active session.
   * - If session is available: uploads immediately
   * - If no session: marks as PENDING (auto-uploads when session available)
   */
  uploadFiles: (files: File[]) => Promise<BuildFile[]>;

  /**
   * Remove a file from the input bar.
   * If the file was uploaded, also deletes from the sandbox.
   */
  removeFile: (fileId: string) => void;

  /**
   * Clear all attached files from the input bar.
   * Does NOT delete from sandbox (use for form reset after send).
   * @param options.suppressRefetch - Unused. Kept so existing callers compile.
   */
  clearFiles: (options?: { suppressRefetch?: boolean }) => void;

  // Check if any files are uploading
  hasUploadingFiles: boolean;

  // Check if any files are pending upload
  hasPendingFiles: boolean;
}

const UploadFilesContext = createContext<UploadFilesContextValue | null>(null);

export interface UploadFilesProviderProps {
  children: ReactNode;
}

export function UploadFilesProvider({ children }: UploadFilesProviderProps) {
  const t = useTranslations("craft.uploadFiles");
  // =========================================================================
  // State
  // =========================================================================

  const [currentMessageFiles, setCurrentMessageFiles] = useState<BuildFile[]>(
    []
  );
  const currentMessageFilesRef = useRef<BuildFile[]>([]);
  const [activeSessionId, setActiveSessionId] = useState<string | null>(null);

  // Get triggerFilesRefresh from the store to refresh the file explorer
  const triggerFilesRefresh = useBuildSessionStore(
    (state) => state.triggerFilesRefresh
  );

  // =========================================================================
  // Refs for race condition protection
  // =========================================================================

  const isUploadingPendingRef = useRef(false);
  const prevSessionRef = useRef<string | null>(null);

  // =========================================================================
  // Derived state
  // =========================================================================

  const hasUploadingFiles = useMemo(() => {
    return currentMessageFiles.some(
      (file) => file.status === UploadFileStatus.UPLOADING
    );
  }, [currentMessageFiles]);

  const hasPendingFiles = useMemo(() => {
    return currentMessageFiles.some(
      (file) => file.status === UploadFileStatus.PENDING
    );
  }, [currentMessageFiles]);

  useEffect(() => {
    currentMessageFilesRef.current = currentMessageFiles;
  }, [currentMessageFiles]);

  // =========================================================================
  // Internal operations (not exposed to consumers)
  // =========================================================================

  /**
   * Upload pending files to the given session.
   * Internal function - called automatically by effects.
   * Reads current files from state internally to avoid stale closures.
   */
  const uploadPendingFilesInternal = useCallback(
    async (sessionId: string): Promise<void> => {
      if (isUploadingPendingRef.current) return;

      const currentFiles = currentMessageFilesRef.current;
      const pendingFiles = currentFiles.filter(
        (f) => f.status === UploadFileStatus.PENDING && f.file
      );

      if (pendingFiles.length === 0) return;

      isUploadingPendingRef.current = true;
      // Functional update so a concurrent add/remove in the same batch is
      // never clobbered. The ref syncs from state in its own effect.
      setCurrentMessageFiles((prev) =>
        prev.map((f) =>
          pendingFiles.some((pf) => pf.id === f.id)
            ? { ...f, status: UploadFileStatus.UPLOADING }
            : f
        )
      );

      try {
        // Upload in parallel
        const results = await Promise.all(
          pendingFiles.map(async (file) => {
            try {
              const result = await uploadFileApi(sessionId, file.file!);
              return { id: file.id, success: true as const, result };
            } catch (error) {
              const { message } = classifyError(error, t);
              return {
                id: file.id,
                success: false as const,
                errorMessage: message,
              };
            }
          })
        );

        // Update statuses
        setCurrentMessageFiles((prev) =>
          prev.map((f) => {
            const result = results.find((r) => r.id === f.id);
            if (!result) return f;
            return result.success
              ? {
                  ...f,
                  status: UploadFileStatus.COMPLETED,
                  path: result.result.path,
                  name: result.result.filename,
                  file: undefined, // Clear blob to free memory
                }
              : {
                  ...f,
                  status: UploadFileStatus.FAILED,
                  error: result.errorMessage,
                };
          })
        );

        // Refresh file explorer if any uploads succeeded
        const anySucceeded = results.some((r) => r.success);
        if (anySucceeded) {
          triggerFilesRefresh(sessionId);
        }
      } finally {
        isUploadingPendingRef.current = false;
      }
    },
    [triggerFilesRefresh, t]
  );

  // =========================================================================
  // Effects - Automatic state machine transitions
  // =========================================================================

  /**
   * Effect: Handle session changes
   *
   * When activeSessionId changes to a different non-null session:
   * - First bind (prev is null): keep local drafts so welcome-page attaches
   *   survive pre-provision bind
   * - Later switch: drop completed chips from the previous session
   *
   * When session becomes null, do not clear files or update the ref.
   * Pre-provisioning can reset to null on focus; drafts must survive that.
   */
  useEffect(() => {
    const prevSession = prevSessionRef.current;
    const currentSession = activeSessionId;

    if (!currentSession || currentSession === prevSession) {
      return;
    }

    prevSessionRef.current = currentSession;

    if (prevSession === null) {
      return;
    }

    setCurrentMessageFiles((prev) =>
      prev.filter(
        (file) =>
          file.status === UploadFileStatus.UPLOADING ||
          file.status === UploadFileStatus.PENDING ||
          file.status === UploadFileStatus.PROCESSING
      )
    );
  }, [activeSessionId]);

  /**
   * Effect: Auto-upload pending files when session becomes available
   *
   * This handles the case where user attaches files before session is ready.
   */
  useEffect(() => {
    if (activeSessionId && hasPendingFiles) {
      uploadPendingFilesInternal(activeSessionId);
    }
  }, [activeSessionId, hasPendingFiles, uploadPendingFilesInternal]);

  // =========================================================================
  // Public API
  // =========================================================================

  /**
   * Set the active session. Drops completed draft chips on a real session switch.
   */
  const setActiveSession = useCallback((sessionId: string | null) => {
    setActiveSessionId(sessionId);
  }, []);

  /**
   * Upload files. Uses activeSessionId internally.
   * Validates files before upload (size, batch limits).
   */
  const uploadFiles = useCallback(
    async (files: File[]): Promise<BuildFile[]> => {
      // Get current files for batch validation
      const existingFiles = currentMessageFiles;

      // Validate batch constraints first
      const batchValidation = validateBatch(files, existingFiles, t);
      if (!batchValidation.valid) {
        // Create failed files for all with the batch error
        const failedFiles = files.map((f) =>
          createFailedFile(f, batchValidation.error!)
        );
        setCurrentMessageFiles((prev) => [...prev, ...failedFiles]);
        return failedFiles;
      }

      // Validate each file individually and separate valid from invalid
      const validFiles: File[] = [];
      const failedFiles: BuildFile[] = [];

      for (const file of files) {
        const validation = validateFile(file, t);
        if (validation.valid) {
          validFiles.push(file);
        } else {
          failedFiles.push(createFailedFile(file, validation.error!));
        }
      }

      // Add failed files immediately
      if (failedFiles.length > 0) {
        setCurrentMessageFiles((prev) => [...prev, ...failedFiles]);
      }

      // If no valid files, return early
      if (validFiles.length === 0) {
        return failedFiles;
      }

      // Create optimistic files for valid files
      const optimisticFiles = validFiles.map(createOptimisticFile);

      // Add to current message files immediately
      setCurrentMessageFiles((prev) => [...prev, ...optimisticFiles]);

      const sessionId = activeSessionId;

      if (sessionId) {
        // Session available - upload immediately
        const uploadPromises = optimisticFiles.map(async (optimisticFile) => {
          try {
            const result = await uploadFileApi(sessionId, optimisticFile.file!);
            return {
              id: optimisticFile.id,
              success: true as const,
              result,
            };
          } catch (error) {
            const { message } = classifyError(error, t);
            return {
              id: optimisticFile.id,
              success: false as const,
              errorMessage: message,
            };
          }
        });

        const results = await Promise.all(uploadPromises);

        // Batch update all file statuses
        setCurrentMessageFiles((prev) =>
          prev.map((f) => {
            const uploadResult = results.find((r) => r.id === f.id);
            if (!uploadResult) return f;

            if (uploadResult.success) {
              return {
                ...f,
                status: UploadFileStatus.COMPLETED,
                path: uploadResult.result.path,
                name: uploadResult.result.filename,
                file: undefined, // Clear blob to free memory
              };
            } else {
              return {
                ...f,
                status: UploadFileStatus.FAILED,
                error: uploadResult.errorMessage,
              };
            }
          })
        );

        // Refresh file explorer if any uploads succeeded
        const anySucceeded = results.some((r) => r.success);
        if (anySucceeded) {
          triggerFilesRefresh(sessionId);
        }
      } else {
        // No session yet - mark as PENDING (effect will auto-upload when session available)
        setCurrentMessageFiles((prev) =>
          prev.map((f) =>
            optimisticFiles.some((of) => of.id === f.id)
              ? { ...f, status: UploadFileStatus.PENDING }
              : f
          )
        );
      }

      return [...failedFiles, ...optimisticFiles];
    },
    [activeSessionId, currentMessageFiles, triggerFilesRefresh, t]
  );

  /**
   * Remove a file. Uses activeSessionId internally for sandbox deletion.
   */
  const removeFile = useCallback(
    (fileId: string) => {
      const currentFiles = currentMessageFilesRef.current;
      const removedIndex = currentFiles.findIndex((f) => f.id === fileId);
      if (removedIndex === -1) {
        return;
      }

      const removedFile = currentFiles[removedIndex];
      if (!removedFile) {
        return;
      }

      setCurrentMessageFiles((prev) => prev.filter((f) => f.id !== fileId));

      if (!removedFile.path || !activeSessionId) {
        return;
      }

      const filePath = removedFile.path;
      const sessionId = activeSessionId;
      const fileToRestore = removedFile;
      const indexToRestore = removedIndex;

      void deleteFileApi(sessionId, filePath)
        .then(() => {
          triggerFilesRefresh(sessionId);
        })
        .catch((error) => {
          const { type } = classifyError(error, t);
          if (type === UploadErrorType.NOT_FOUND) {
            triggerFilesRefresh(sessionId);
            return;
          }
          console.error(
            "[UploadFilesContext] Failed to delete file from sandbox:",
            error
          );
          setCurrentMessageFiles((prev) => {
            if (prev.some((f) => f.id === fileToRestore.id)) return prev;

            const newFiles = [...prev];
            const insertIndex = Math.min(indexToRestore, newFiles.length);
            newFiles.splice(insertIndex, 0, fileToRestore);
            return newFiles;
          });
        });
    },
    [activeSessionId, triggerFilesRefresh, t]
  );

  /**
   * Clear all files from the input bar.
   */
  const clearFiles = useCallback((_options?: { suppressRefetch?: boolean }) => {
    setCurrentMessageFiles([]);
  }, []);

  // =========================================================================
  // Context value
  // =========================================================================

  const value = useMemo<UploadFilesContextValue>(
    () => ({
      currentMessageFiles,
      activeSessionId,
      setActiveSession,
      uploadFiles,
      removeFile,
      clearFiles,
      hasUploadingFiles,
      hasPendingFiles,
    }),
    [
      currentMessageFiles,
      activeSessionId,
      setActiveSession,
      uploadFiles,
      removeFile,
      clearFiles,
      hasUploadingFiles,
      hasPendingFiles,
    ]
  );

  return (
    <UploadFilesContext.Provider value={value}>
      {children}
    </UploadFilesContext.Provider>
  );
}

export function useUploadFilesContext() {
  const context = useContext(UploadFilesContext);
  if (!context) {
    throw new Error(
      "useUploadFilesContext must be used within an UploadFilesProvider"
    );
  }
  return context;
}
