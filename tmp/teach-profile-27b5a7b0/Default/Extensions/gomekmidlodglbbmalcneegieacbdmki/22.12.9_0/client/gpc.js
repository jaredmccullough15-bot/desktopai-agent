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

  // src/core/assets/command/GetAssetPathQuery.ts
  var GetAssetPathQuery = class extends Command {
    constructor(path) {
      super();
      this.path = path;
    }
    execute() {
      return chrome.runtime.getURL(this.path);
    }
  };

  // src/client/scripting/error/ClientScriptContentInjectionError.ts
  var ClientScriptContentInjectionError = class {
    constructor(message) {
      this.message = message;
      this.name = "ClientScriptContentInjectionError";
    }
  };

  // src/client/scripting/command/InjectClientScriptContentCommand.ts
  var InjectClientScriptContentCommand = class extends Command {
    constructor(path) {
      super();
      this.path = path;
    }
    execute() {
      return __async(this, null, function* () {
        try {
          return this.injectScript();
        } catch (e) {
          return Promise.reject(new ClientScriptContentInjectionError(e.message));
        }
      });
    }
    injectScript() {
      const scriptElement = document.createElement("script");
      const documentElement = document.documentElement;
      scriptElement.src = new GetAssetPathQuery(this.path).execute();
      documentElement.insertBefore(scriptElement, documentElement.firstChild);
      documentElement.removeChild(scriptElement);
    }
  };

  // src/modules/gpc/client/GlobalPrivacyControlClient.ts
  var GlobalPrivacyControlClient = class {
    static injectContentScript() {
      return __async(this, null, function* () {
        try {
          const gpcEnabled = yield new ClientMessageQuery("globalPrivacyControl.getState" /* GET_STATE */).execute();
          if (gpcEnabled)
            yield new InjectClientScriptContentCommand("client/gpcWindowSetting.js").execute();
        } catch (e) {
        }
      });
    }
  };

  // src/modules/gpc/client/script/GlobalPrivacyControlContentScript.ts
  GlobalPrivacyControlClient.injectContentScript();
})();
