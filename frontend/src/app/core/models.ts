export interface AuthResponse {
  access_token: string;
  token_type: string;
  csrf_token: string;
}

export interface Project {
  id: string;
  name: string;
  description: string;
  created_at: string;
}

export interface Requirement {
  id: string;
  project_id: string;
  requirement_key: string;
  title: string;
  description: string;
  acceptance_criteria: string;
  created_at: string;
}

export interface TestCase {
  id: string;
  case_key: string;
  requirement_id: string;
  scenario: string;
  preconditions: string;
  steps: string[];
  expected_result: string;
  test_data: Record<string, unknown>;
  priority: 'P0' | 'P1' | 'P2';
  severity: string;
  test_type: string;
  automation_feasibility: string;
  tags: string[];
  status: string;
}

export interface Dashboard {
  total_requirements: number;
  total_test_cases: number;
  coverage_percent: number;
  covered_requirements: number;
  duplicate_test_cases: number;
  automation_readiness_percent: number;
  priority_distribution: Record<string, number>;
  defect_prediction_score: number;
}

export interface PageOfTestCases {
  items: TestCase[];
  total: number;
  page: number;
  page_size: number;
}
