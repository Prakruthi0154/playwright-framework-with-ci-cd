import { Injectable } from '@angular/core';
import { HttpClient, HttpParams } from '@angular/common/http';
import { Observable } from 'rxjs';
import { Dashboard, PageOfTestCases, Project, Requirement, TestCase } from './models';

@Injectable({ providedIn: 'root' })
export class ApiService {
  constructor(private readonly http: HttpClient) {}

  projects(): Observable<Project[]> {
    return this.http.get<Project[]>('/api/v1/projects');
  }

  createProject(name: string, description: string): Observable<Project> {
    return this.http.post<Project>('/api/v1/projects', { name, description });
  }

  requirements(projectId: string): Observable<Requirement[]> {
    return this.http.get<Requirement[]>(`/api/v1/projects/${projectId}/requirements`);
  }

  createRequirement(projectId: string, requirement: Pick<Requirement, 'requirement_key' | 'title' | 'description' | 'acceptance_criteria'>): Observable<Requirement> {
    return this.http.post<Requirement>(`/api/v1/projects/${projectId}/requirements`, requirement);
  }

  uploadRequirement(projectId: string, file: File): Observable<Requirement> {
    const form = new FormData();
    form.append('file', file);
    return this.http.post<Requirement>(`/api/v1/projects/${projectId}/requirements/import`, form);
  }

  importRequirementsCsv(projectId: string, file: File): Observable<{ imported: number; requirements: Requirement[] }> {
    const form = new FormData();
    form.append('file', file);
    return this.http.post<{ imported: number; requirements: Requirement[] }>(
      `/api/v1/projects/${projectId}/requirements/import-bulk`,
      form
    );
  }

  generate(requirementId: string): Observable<TestCase[]> {
    return this.http.post<TestCase[]>(`/api/v1/requirements/${requirementId}/generate`, {});
  }

  testCases(projectId: string, page = 1, q = ''): Observable<PageOfTestCases> {
    let params = new HttpParams().set('page', page).set('page_size', 50);
    if (q.trim()) params = params.set('q', q.trim());
    return this.http.get<PageOfTestCases>(`/api/v1/projects/${projectId}/test-cases`, { params });
  }

  dashboard(projectId: string): Observable<Dashboard> {
    return this.http.get<Dashboard>(`/api/v1/projects/${projectId}/dashboard`);
  }

  exportUrl(projectId: string, format: 'csv' | 'xlsx' | 'pdf'): string {
    return `/api/v1/projects/${projectId}/exports/${format}`;
  }

  export(projectId: string, format: 'csv' | 'xlsx' | 'pdf'): Observable<Blob> {
    return this.http.get(this.exportUrl(projectId, format), { responseType: 'blob' });
  }
}
