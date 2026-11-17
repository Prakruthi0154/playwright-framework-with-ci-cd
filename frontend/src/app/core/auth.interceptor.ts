import { HttpInterceptorFn } from '@angular/common/http';
import { inject } from '@angular/core';
import { HttpErrorResponse } from '@angular/common/http';
import { catchError, switchMap, throwError } from 'rxjs';
import { AuthService } from './auth.service';

export const authInterceptor: HttpInterceptorFn = (request, next) => {
  const auth = inject(AuthService);
  const token = auth.token();
  if (!token || !request.url.startsWith('/api/v1/') || request.url.includes('/auth/')) {
    return next(request);
  }
  return next(request.clone({ setHeaders: { Authorization: `Bearer ${token}` } })).pipe(
    catchError((error: unknown) => {
      if (!(error instanceof HttpErrorResponse) || error.status !== 401 || request.url.includes('/auth/')) {
        return throwError(() => error);
      }
      return auth.refresh().pipe(
        switchMap(response => next(request.clone({
          setHeaders: { Authorization: `Bearer ${response.access_token}` }
        }))),
        catchError(refreshError => {
          auth.clear();
          return throwError(() => refreshError);
        })
      );
    })
  );
};
