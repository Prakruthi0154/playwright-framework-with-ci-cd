import { TestBed } from '@angular/core/testing';
import { provideHttpClient } from '@angular/common/http';
import { HttpTestingController, provideHttpClientTesting } from '@angular/common/http/testing';
import { ApiService } from './api.service';

describe('ApiService', () => {
  let api: ApiService;
  let http: HttpTestingController;

  beforeEach(() => {
    TestBed.configureTestingModule({
      providers: [provideHttpClient(), provideHttpClientTesting()]
    });
    api = TestBed.inject(ApiService);
    http = TestBed.inject(HttpTestingController);
  });

  afterEach(() => http.verify());

  it('lists and creates projects', () => {
    api.projects().subscribe();
    const listed = http.expectOne('/api/v1/projects');
    expect(listed.request.method).toBe('GET');
    listed.flush([]);
    api.createProject('Payments', 'Checkout flow').subscribe();
    const request = http.expectOne('/api/v1/projects');
    expect(request.request.body).toEqual({ name: 'Payments', description: 'Checkout flow' });
    request.flush({ id: 'p1', name: 'Payments', description: 'Checkout flow', created_at: '' });
  });

  it('creates requirements and uploads a document', () => {
    api.requirements('p1').subscribe();
    const listed = http.expectOne('/api/v1/projects/p1/requirements');
    expect(listed.request.method).toBe('GET');
    listed.flush([]);
    api.createRequirement('p1', {
      requirement_key: 'AUTH-1',
      title: 'Sign in',
      description: 'Users sign in',
      acceptance_criteria: 'Valid credentials work'
    }).subscribe();
    const created = http.expectOne('/api/v1/projects/p1/requirements');
    expect(created.request.method).toBe('POST');
    created.flush({ id: 'r1' });
    api.uploadRequirement('p1', new File(['story'], 'story.txt')).subscribe();
    const upload = http.expectOne('/api/v1/projects/p1/requirements/import');
    expect(upload.request.body instanceof FormData).toBe(true);
    upload.flush({ id: 'r1' });
    api.importRequirementsCsv('p1', new File(['requirement_key,title,description'], 'requirements.csv')).subscribe();
    const bulk = http.expectOne('/api/v1/projects/p1/requirements/import-bulk');
    expect(bulk.request.body instanceof FormData).toBe(true);
    bulk.flush({ imported: 0, requirements: [] });
  });

  it('generates, filters, and exports cases', () => {
    api.generate('r1').subscribe();
    const generated = http.expectOne('/api/v1/requirements/r1/generate');
    expect(generated.request.method).toBe('POST');
    generated.flush([]);

    api.testCases('p1').subscribe();
    const unfiltered = http.expectOne(request => request.url === '/api/v1/projects/p1/test-cases');
    expect(unfiltered.request.params.get('page_size')).toBe('50');
    unfiltered.flush({ items: [], total: 0, page: 1, page_size: 50 });
    api.testCases('p1', 2, 'login').subscribe();
    const filtered = http.expectOne(request => request.url === '/api/v1/projects/p1/test-cases');
    expect(filtered.request.params.get('q')).toBe('login');
    expect(filtered.request.params.get('page')).toBe('2');
    filtered.flush({ items: [], total: 0, page: 2, page_size: 50 });
    api.dashboard('p1').subscribe();
    const dashboard = http.expectOne('/api/v1/projects/p1/dashboard');
    expect(dashboard.request.method).toBe('GET');
    dashboard.flush({});

    expect(api.exportUrl('p1', 'xlsx')).toBe('/api/v1/projects/p1/exports/xlsx');
    api.export('p1', 'csv').subscribe();
    const exported = http.expectOne('/api/v1/projects/p1/exports/csv');
    expect(exported.request.responseType).toBe('blob');
    exported.flush(new Blob(['csv']));
  });
});
