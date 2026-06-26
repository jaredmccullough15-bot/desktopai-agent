(() => {
  var __async = (__this, __arguments, generator) => {
    return new Promise((resolve, reject) => {
      var fulfilled = (value) => {
        try {
          step(generator.next(value));
        } catch (e) {
          reject(e);
        }
      };
      var rejected = (value) => {
        try {
          step(generator.throw(value));
        } catch (e) {
          reject(e);
        }
      };
      var step = (x) => x.done ? resolve(x.value) : Promise.resolve(x.value).then(fulfilled, rejected);
      step((generator = generator.apply(__this, __arguments)).next());
    });
  };

  // src/core/command/Command.ts
  var Command = class {
  };

  // src/core/messages/error/MessageNotSentError.ts
  var MessageNotSentError = class {
    constructor(message, messageName, error) {
      this.message = message;
      this.messageName = messageName;
      this.error = error;
      this.name = "MessageNotSentError";
    }
  };

  // src/core/messages/command/MessageQueryBase.ts
  var MessageQueryBase = class extends Command {
    constructor(name, body, target) {
      super();
      this.message = { name, body, target };
    }
    execute() {
      return __async(this, null, function* () {
        try {
          return yield this.sendMessage();
        } catch (e) {
          return Promise.reject(new MessageNotSentError(e.message, this.message.name));
        }
      });
    }
  };

  // src/client/messages/command/ClientMessageQuery.ts
  var ClientMessageQuery = class extends MessageQueryBase {
    constructor(name, body = {}, callback, target = "BACKGROUND" /* BACKGROUND */) {
      super(name, body, target);
      this.callback = callback;
    }
    sendMessage() {
      return __async(this, null, function* () {
        return chrome.runtime.sendMessage(this.message, this.callback);
      });
    }
  };

  // src/modules/cookieConsent/client/script/CookieConsentContentScript.ts
  var isIFrame = window.self !== window.top;
  new ClientMessageQuery("cookieManager.injectClientScript" /* INJECT_SCRIPT */, { isIFrame }).execute();
})();
