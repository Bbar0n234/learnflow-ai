import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { apiClient } from "./client";
import { queryKeys } from "./query-keys";

// === Types ===

export interface SkillContextDocument {
  key: string;
  description: string;
  content: string;
  created_at: string;
  updated_at: string;
}

export interface SkillGroup {
  skill_name: string;
  in_library: boolean;
  documents: SkillContextDocument[];
}

export interface SkillContextsResponse {
  skills: SkillGroup[];
}

export interface UpdateSkillContextPayload {
  description: string;
  content: string;
}

// === API ===

export async function getSkillContexts(): Promise<SkillContextsResponse> {
  const { data } = await apiClient.get("/users/me/skill-contexts");
  return data;
}

export async function updateSkillContext(
  skillName: string,
  key: string,
  payload: UpdateSkillContextPayload,
): Promise<SkillContextDocument> {
  const { data } = await apiClient.put(
    `/users/me/skill-contexts/${encodeURIComponent(skillName)}/${encodeURIComponent(key)}`,
    payload,
  );
  return data;
}

export async function deleteSkillContext(
  skillName: string,
  key: string,
): Promise<void> {
  await apiClient.delete(
    `/users/me/skill-contexts/${encodeURIComponent(skillName)}/${encodeURIComponent(key)}`,
  );
}

// === Hooks ===

export function useSkillContexts() {
  return useQuery({
    queryKey: queryKeys.skillContexts,
    queryFn: getSkillContexts,
  });
}

export function useUpdateSkillContext() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({
      skillName,
      key,
      payload,
    }: {
      skillName: string;
      key: string;
      payload: UpdateSkillContextPayload;
    }) => updateSkillContext(skillName, key, payload),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: queryKeys.skillContexts });
    },
  });
}

export function useDeleteSkillContext() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ skillName, key }: { skillName: string; key: string }) =>
      deleteSkillContext(skillName, key),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: queryKeys.skillContexts });
    },
  });
}
