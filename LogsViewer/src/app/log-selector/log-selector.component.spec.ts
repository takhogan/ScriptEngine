import { ComponentFixture, TestBed } from '@angular/core/testing';

import { LogSelectorComponent } from './log-selector.component';

describe('LogSelectorComponent', () => {
  let component: LogSelectorComponent;
  let fixture: ComponentFixture<LogSelectorComponent>;

  beforeEach(async () => {
    await TestBed.configureTestingModule({
      declarations: [ LogSelectorComponent ]
    })
    .compileComponents();

    fixture = TestBed.createComponent(LogSelectorComponent);
    component = fixture.componentInstance;
    fixture.detectChanges();
  });

  it('should create', () => {
    expect(component).toBeTruthy();
  });
});
