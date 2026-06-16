// Канонический envelope списочных ответов main app: items + pagination metadata.
export interface ListResponse<T> {
  items: T[];
  total: number;
  limit: number;
  offset: number;
}
