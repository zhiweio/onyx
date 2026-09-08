import { LongTermMemoryItem } from "@/lib/types";

export async function listLongTermMemories(): Promise<LongTermMemoryItem[]> {
  const response = await fetch("/api/long-term-memory", { method: "GET" });
  if (!response.ok) {
    throw new Error("Failed to list long-term memories");
  }
  const payload = (await response.json()) as { items: LongTermMemoryItem[] };
  return payload.items;
}

export async function createLongTermMemory(
  text: string
): Promise<LongTermMemoryItem> {
  const response = await fetch("/api/long-term-memory", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ text }),
  });
  if (!response.ok) {
    throw new Error("Failed to create long-term memory");
  }
  return (await response.json()) as LongTermMemoryItem;
}

export async function updateLongTermMemory(
  id: number,
  text: string
): Promise<LongTermMemoryItem> {
  const response = await fetch(`/api/long-term-memory/${id}`, {
    method: "PATCH",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ text }),
  });
  if (!response.ok) {
    throw new Error("Failed to update long-term memory");
  }
  return (await response.json()) as LongTermMemoryItem;
}

export async function deleteLongTermMemory(id: number): Promise<void> {
  const response = await fetch(`/api/long-term-memory/${id}`, {
    method: "DELETE",
  });
  if (!response.ok) {
    throw new Error("Failed to delete long-term memory");
  }
}
