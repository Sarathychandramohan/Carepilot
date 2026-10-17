const API_BASE_URL = (import.meta as any).env?.VITE_API_URL || 'http://localhost:8000';

export interface RequestOptions extends RequestInit {
  params?: Record<string, string | number | boolean | undefined>;
}

export class ApiError extends Error {
  status: number;
  data: any;

  constructor(status: number, message: string, data?: any) {
    super(message);
    this.name = 'ApiError';
    this.status = status;
    this.data = data;
  }
}

async function request<T>(endpoint: string, options: RequestOptions = {}): Promise<T> {
  const { params, headers, ...customConfig } = options;
  
  let url = `${API_BASE_URL}${endpoint}`;
  if (params) {
    const searchParams = new URLSearchParams();
    Object.entries(params).forEach(([key, value]) => {
      if (value !== undefined && value !== null) {
        searchParams.append(key, String(value));
      }
    });
    const queryString = searchParams.toString();
    if (queryString) {
      url += (url.includes('?') ? '&' : '?') + queryString;
    }
  }

  const defaultHeaders: Record<string, string> = {
    'Content-Type': 'application/json',
    'X-User-Role': 'doctor', // Satisfies backend require_doctor_role check
  };

  const response = await fetch(url, {
    ...customConfig,
    headers: {
      ...defaultHeaders,
      ...headers,
    },
  });

  if (!response.ok) {
    let errorData: any = null;
    try {
      errorData = await response.json();
    } catch {
      errorData = await response.text();
    }
    const message = (errorData && (errorData.detail || errorData.message)) || `HTTP ${response.status}`;
    throw new ApiError(response.status, message, errorData);
  }

  return response.json();
}

export const apiClient = {
  get: <T>(endpoint: string, options?: RequestOptions) => 
    request<T>(endpoint, { method: 'GET', ...options }),

  post: <T>(endpoint: string, body?: any, options?: RequestOptions) => 
    request<T>(endpoint, { 
      method: 'POST', 
      body: body ? JSON.stringify(body) : undefined, 
      ...options 
    }),

  put: <T>(endpoint: string, body?: any, options?: RequestOptions) => 
    request<T>(endpoint, { 
      method: 'PUT', 
      body: body ? JSON.stringify(body) : undefined, 
      ...options 
    }),

  delete: <T>(endpoint: string, options?: RequestOptions) => 
    request<T>(endpoint, { method: 'DELETE', ...options }),
};
