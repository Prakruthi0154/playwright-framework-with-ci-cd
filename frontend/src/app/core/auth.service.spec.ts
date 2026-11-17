import { TestBed } from '@angular/core/testing';
import { provideHttpClient } from '@angular/common/http';
import { HttpTestingController, provideHttpClientTesting } from '@angular/common/http/testing';
import { AuthService } from './auth.service';
import { AuthResponse } from './models';

const authResponse: AuthResponse = { access_token: 'access-1', token_type: 'bearer', csrf_token: 'csrf-1' };

describe('AuthService', () => {
  let auth: AuthService;
  let http: HttpTestingController;

  beforeEach(() => {
    TestBed.configureTestingModule({
      providers: [provideHttpClient(), provideHttpClientTesting()]
    });
    auth = TestBed.inject(AuthService);
    http = TestBed.inject(HttpTestingController);
  });

  afterEach(() => http.verify());

  it('accepts login and registration tokens in memory', () => {
    auth.login('qa@example.com', 'password').subscribe();
    http.expectOne('/api/v1/auth/login').flush(authResponse);
    expect(auth.token()).toBe('access-1');
    expect(auth.csrfToken()).toBe('csrf-1');

    auth.register('qa@example.com', 'QA User', 'strong-password').subscribe();
    const request = http.expectOne('/api/v1/auth/register');
    expect(request.request.body.full_name).toBe('QA User');
    request.flush({ ...authResponse, access_token: 'access-2' });
    expect(auth.token()).toBe('access-2');
  });

  it('sends the CSRF token for refresh and coalesces concurrent refreshes', () => {
    auth.csrfToken.set('csrf-1');
    auth.refresh().subscribe();
    auth.refresh().subscribe();
    const request = http.expectOne('/api/v1/auth/refresh');
    expect(request.request.withCredentials).toBe(true);
    expect(request.request.headers.get('X-CSRF-Token')).toBe('csrf-1');
    request.flush(authResponse);
    expect(auth.token()).toBe('access-1');
  });

  it('clears local credentials after logout completes', () => {
    auth.token.set('access-1');
    auth.csrfToken.set('csrf-1');
    auth.logout().subscribe();
    const request = http.expectOne('/api/v1/auth/logout');
    expect(request.request.headers.get('X-CSRF-Token')).toBe('csrf-1');
    request.flush(null);
    expect(auth.token()).toBeNull();
    expect(auth.csrfToken()).toBeNull();
  });

  it('restores the CSRF token from the readable cookie', () => {
    document.cookie = 'csrf_token=; max-age=0; path=/';
    expect(auth.restoreCsrfToken()).toBe(false);
    document.cookie = 'csrf_token=restored-csrf; path=/';
    expect(auth.restoreCsrfToken()).toBe(true);
    expect(auth.csrfToken()).toBe('restored-csrf');
  });
});
