import { useState, useCallback } from 'react';
import type { ApiError } from '../services/types';

export const useApi = () => {
  const [isLoading, setIsLoading] = useState<boolean>(false);
  const [error, setError] = useState<ApiError | null>(null);

  const executeRequest = useCallback(async <T>(
    request: Promise<T>
  ): Promise<T | null> => {
    setIsLoading(true);
    setError(null);

    try {
      const result = await request;
      return result;
    } catch (err) {
      const apiError = err as ApiError;
      setError(apiError);
      console.error('API request failed:', apiError);
      return null;
    } finally {
      setIsLoading(false);
    }
  }, []);

  const clearError = useCallback(() => {
    setError(null);
  }, []);

  return {
    isLoading,
    error,
    executeRequest,
    clearError,
  };
};