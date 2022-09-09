import { Component, EventEmitter, Input, OnDestroy, OnInit, Output } from '@angular/core';
import { LogObject } from '../../types/log-viewer-types';
import { Subscription } from 'rxjs';

@Component({
  selector: 'app-log-selector',
  templateUrl: './log-selector.component.html',
  styleUrls: ['./log-selector.component.css']
})
export class LogSelectorComponent implements OnDestroy, OnInit {

  @Input() logList : Array<LogObject>;
  private selectedLogIndex : number;

  constructor(private logLoader : LogLoaderService) { }

  ngOnInit(): void {
    this.sub.push(this.logLoader.selectedLogIndex$.subscribe(logIndex => {
      this.selectedLogIndex = logIndex;
    }));
  }

  ngOnDestory() {
    this.subs.forEach(sub => {
      sub.unsubscribe();
    });
  }

  onLogSelect(logIndex) {
    this.logLoader.updateSelectedLogIndex(logIndex);
  }



}
