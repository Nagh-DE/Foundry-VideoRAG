import { useQuery } from '@tanstack/react-query';
import { getProcessingStatus } from '../services/api';
import type { ProcessingStatus } from '../types';

export function useProcessingStatus(videoId: string | undefined) {
  return useQuery({
    queryKey: ['processing-status', videoId],
    queryFn: () => getProcessingStatus(videoId!),
    enabled: !!videoId,
    refetchInterval: (query) => {
      const data = query.state.data as ProcessingStatus | undefined;
      if (data?.status === 'ready' || data?.status === 'failed') return false;
      return 3000;
    },
  });
}
