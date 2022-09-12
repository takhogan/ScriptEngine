import { Component, EventEmitter, Input, OnDestroy, OnInit, Output } from '@angular/core';
import { LogObject } from '../../types/log-viewer-types';
import { Subscription } from 'rxjs';
import { LogLoaderService } from '../../log-loader.service';


@Component({
  selector: 'app-log-selector',
  templateUrl: './log-selector.component.html',
  styleUrls: ['./log-selector.component.css']
})
export class LogSelectorComponent implements OnDestroy, OnInit {

  @Input() logList : Array<LogObject>;
  selectedLogIndex : number | null;

  private subs : Array<Subscription>;

  constructor(private logLoader : LogLoaderService) {
    this.logList = [];
    this.selectedLogIndex = null;
    this.subs = [];
  }

  ngOnInit(): void {
    this.subs.push(this.logLoader.selectedLogIndex$.subscribe(logIndex => {
      this.selectedLogIndex = logIndex;
    }));
  }

  ngOnDestroy() {
    this.subs.forEach(sub => {
      sub.unsubscribe();
    });
  }

  onLogSelect(logIndex : number) {
    this.logLoader.updateSelectedLogIndex(logIndex);
  }



}
