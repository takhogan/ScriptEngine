import { ComponentFixture, TestBed } from '@angular/core/testing';

import { LogNavbarComponent } from './log-navbar.component';

describe('LogNavbarComponent', () => {
  let component: LogNavbarComponent;
  let fixture: ComponentFixture<LogNavbarComponent>;

  beforeEach(async () => {
    await TestBed.configureTestingModule({
      declarations: [ LogNavbarComponent ]
    })
    .compileComponents();

    fixture = TestBed.createComponent(LogNavbarComponent);
    component = fixture.componentInstance;
    fixture.detectChanges();
  });

  it('should create', () => {
    expect(component).toBeTruthy();
  });
});
