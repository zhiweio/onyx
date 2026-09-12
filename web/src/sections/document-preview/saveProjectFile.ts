import { replaceCraftProjectFile } from "@/lib/craft-projects/api";
import { replaceUserFile } from "@/lib/projects/svc";

export async function saveCraftProjectFileBytes(
  projectId: string,
  fileId: string,
  fileName: string,
  bytes: Uint8Array,
  mimeType: string
): Promise<void> {
  const file = new File([bytes], fileName, { type: mimeType });
  await replaceCraftProjectFile(projectId, fileId, file);
}

export async function saveChatProjectFileBytes(
  fileId: string,
  fileName: string,
  bytes: Uint8Array,
  mimeType: string
): Promise<void> {
  const file = new File([bytes], fileName, { type: mimeType });
  await replaceUserFile(fileId, file);
}
