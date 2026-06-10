import { apiClient } from './client';

export async function getPendingReviews() {
  const res = await apiClient.get("/reviews/pending");
  return res.data;
}

export async function getReviewDetail(submissionId: number | string) {
  const res = await apiClient.get(`/reviews/${submissionId}`);
  return res.data;
}

export async function getReviewViewModel(submissionId: number | string) {
  const res = await apiClient.get(`/reviews/${submissionId}/view-model`);
  return res.data;
}

export async function approveReview(
  submissionId: number | string,
  data: { comments: string }
) {
  const res = await apiClient.post(
    `/reviews/${submissionId}/approve`,
    {
      reviewer_id: 1,
      comment: data.comments
    }
  );
  return res.data;
}

export async function rejectReview(
  submissionId: number | string,
  data: { comments: string }
) {
  const res = await apiClient.post(
    `/reviews/${submissionId}/reject`,
    {
      reviewer_id: 1,
      comment: data.comments
    }
  );
  return res.data;
}

export async function reviseReview(
  submissionId: number | string,
  data: { comments?: string; revised_data: Record<string, unknown> }
) {
  const res = await apiClient.post(
    `/reviews/${submissionId}/revise?reviewer_id=3`,
    data
  );
  return res.data;
}
