import { TestBed } from '@angular/core/testing';
import { HttpClient, provideHttpClient, withInterceptors } from '@angular/common/http';
import { HttpTestingController, provideHttpClientTesting } from '@angular/common/http/testing';
import { HttpErrorResponse } from '@angular/common/http';
import { firstValueFrom } from 'rxjs';
import { authInterceptor } from './auth.interceptor';
import { AuthService } from './auth.service';

describe('authInterceptor', () => {
  let client: HttpClient;
  let http: HttpTestingController;
  let auth: AuthService;

  beforeEach(() => {
    TestBed.configureTestingModule({
      providers: [
        provideHttpClient(withInterceptors([authInterceptor])),
        provideHttpClientTesting()
      ]
    });
    client = TestBed.inject(HttpClient);
    http = TestBed.inject(HttpTestingController);
    auth = TestBed.inject(AuthService);
  });

  afterEach(() => http.verify());

  it('passes through unauthenticated and authentication requests', () => {
    client.get('/api/v1/projects').subscribe();
    const projects = http.expectOne('/api/v1/projects');
    expect(projects.request.headers.has('Authorization')).toBe(false);
    projects.flush([]);
    auth.token.set('old-token');
    client.post('/api/v1/auth/login', {}).subscribe();
    const login = http.expectOne('/api/v1/auth/login');
    expect(login.request.headers.has('Authorization')).toBe(false);
    login.flush({});
  });

  it('refreshes an expired access token and retries the request', async () => {
    auth.token.set('expired-token');
    auth.csrfToken.set('csrf');
    const result = firstValueFrom(client.get('/api/v1/projects'));
    http.expectOne('/api/v1/projects').flush({}, { status: 401, statusText: 'Unauthorized' });
    const refresh = http.expectOne('/api/v1/auth/refresh');
    refresh.flush({ access_token: 'new-token', token_type: 'bearer', csrf_token: 'new-csrf' });
    const retry = http.expectOne('/api/v1/projects');
    expect(retry.request.headers.get('Authorization')).toBe('Bearer new-token');
    retry.flush([]);
    await expect(result).resolves.toEqual([]);
    expect(auth.token()).toBe('new-token');
  });

  it('clears credentials when refresh fails', async () => {
    auth.token.set('expired-token');
    auth.csrfToken.set('csrf');
    const result = firstValueFrom(client.get('/api/v1/projects'));
    http.expectOne('/api/v1/projects').flush({}, { status: 401, statusText: 'Unauthorized' });
    http.expectOne('/api/v1/auth/refresh').flush({}, { status: 401, statusText: 'Unauthorized' });
    await expect(result).rejects.toBeInstanceOf(HttpErrorResponse);
    expect(auth.token()).toBeNull();
  });
});
