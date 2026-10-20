import { bootstrapApplication } from '@angular/platform-browser';
import { DemoApp } from './demo/app';
bootstrapApplication(DemoApp).catch(error => console.error('ExpertAI could not start', error));
