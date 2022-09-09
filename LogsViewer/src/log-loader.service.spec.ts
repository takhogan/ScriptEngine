import { TestBed } from '@angular/core/testing';

import { LogLoaderService } from './log-loader.service';

describe('LogLoaderService', () => {
  let service: LogLoaderService;

  beforeEach(() => {
    TestBed.configureTestingModule({});
    service = TestBed.inject(LogLoaderService);
  });

  it('should be created', () => {
    expect(service).toBeTruthy();
  });
});
