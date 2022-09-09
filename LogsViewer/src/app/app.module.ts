import { NgModule } from '@angular/core';
import { BrowserModule } from '@angular/platform-browser';

import { AppComponent } from './app.component';
import { LogSelectorComponent } from './log-selector/log-selector.component';
import { LogViewerComponent } from './log-viewer/log-viewer.component';
import { LogNavbarComponent } from './log-navbar/log-navbar.component';

@NgModule({
  declarations: [
    AppComponent,
    LogSelectorComponent,
    LogViewerComponent,
    LogNavbarComponent
  ],
  imports: [
    BrowserModule
  ],
  providers: [],
  bootstrap: [AppComponent]
})
export class AppModule { }
