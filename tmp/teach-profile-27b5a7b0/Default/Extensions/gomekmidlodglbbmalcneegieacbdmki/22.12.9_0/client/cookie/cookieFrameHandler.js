(() => {
  var __create = Object.create;
  var __defProp = Object.defineProperty;
  var __defProps = Object.defineProperties;
  var __getOwnPropDesc = Object.getOwnPropertyDescriptor;
  var __getOwnPropDescs = Object.getOwnPropertyDescriptors;
  var __getOwnPropNames = Object.getOwnPropertyNames;
  var __getOwnPropSymbols = Object.getOwnPropertySymbols;
  var __getProtoOf = Object.getPrototypeOf;
  var __hasOwnProp = Object.prototype.hasOwnProperty;
  var __propIsEnum = Object.prototype.propertyIsEnumerable;
  var __defNormalProp = (obj, key, value) => key in obj ? __defProp(obj, key, { enumerable: true, configurable: true, writable: true, value }) : obj[key] = value;
  var __spreadValues = (a, b) => {
    for (var prop in b || (b = {}))
      if (__hasOwnProp.call(b, prop))
        __defNormalProp(a, prop, b[prop]);
    if (__getOwnPropSymbols)
      for (var prop of __getOwnPropSymbols(b)) {
        if (__propIsEnum.call(b, prop))
          __defNormalProp(a, prop, b[prop]);
      }
    return a;
  };
  var __spreadProps = (a, b) => __defProps(a, __getOwnPropDescs(b));
  var __commonJS = (cb, mod) => function __require() {
    return mod || (0, cb[__getOwnPropNames(cb)[0]])((mod = { exports: {} }).exports, mod), mod.exports;
  };
  var __copyProps = (to, from, except, desc) => {
    if (from && typeof from === "object" || typeof from === "function") {
      for (let key of __getOwnPropNames(from))
        if (!__hasOwnProp.call(to, key) && key !== except)
          __defProp(to, key, { get: () => from[key], enumerable: !(desc = __getOwnPropDesc(from, key)) || desc.enumerable });
    }
    return to;
  };
  var __toESM = (mod, isNodeMode, target) => (target = mod != null ? __create(__getProtoOf(mod)) : {}, __copyProps(
    isNodeMode || !mod || !mod.__esModule ? __defProp(target, "default", { value: mod, enumerable: true }) : target,
    mod
  ));
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

  // node_modules/tslib/tslib.js
  var require_tslib = __commonJS({
    "node_modules/tslib/tslib.js"(exports, module) {
      var __extends3;
      var __assign3;
      var __rest2;
      var __decorate2;
      var __param2;
      var __metadata2;
      var __awaiter3;
      var __generator3;
      var __exportStar2;
      var __values3;
      var __read2;
      var __spread2;
      var __spreadArrays2;
      var __await2;
      var __asyncGenerator2;
      var __asyncDelegator2;
      var __asyncValues3;
      var __makeTemplateObject2;
      var __importStar2;
      var __importDefault2;
      var __classPrivateFieldGet2;
      var __classPrivateFieldSet2;
      var __createBinding2;
      (function(factory) {
        var root = typeof global === "object" ? global : typeof self === "object" ? self : typeof this === "object" ? this : {};
        if (typeof define === "function" && define.amd) {
          define("tslib", ["exports"], function(exports2) {
            factory(createExporter(root, createExporter(exports2)));
          });
        } else if (typeof module === "object" && typeof module.exports === "object") {
          factory(createExporter(root, createExporter(module.exports)));
        } else {
          factory(createExporter(root));
        }
        function createExporter(exports2, previous) {
          if (exports2 !== root) {
            if (typeof Object.create === "function") {
              Object.defineProperty(exports2, "__esModule", { value: true });
            } else {
              exports2.__esModule = true;
            }
          }
          return function(id, v) {
            return exports2[id] = previous ? previous(id, v) : v;
          };
        }
      })(function(exporter) {
        var extendStatics2 = Object.setPrototypeOf || { __proto__: [] } instanceof Array && function(d, b) {
          d.__proto__ = b;
        } || function(d, b) {
          for (var p in b)
            if (b.hasOwnProperty(p))
              d[p] = b[p];
        };
        __extends3 = function(d, b) {
          extendStatics2(d, b);
          function __() {
            this.constructor = d;
          }
          d.prototype = b === null ? Object.create(b) : (__.prototype = b.prototype, new __());
        };
        __assign3 = Object.assign || function(t) {
          for (var s, i = 1, n = arguments.length; i < n; i++) {
            s = arguments[i];
            for (var p in s)
              if (Object.prototype.hasOwnProperty.call(s, p))
                t[p] = s[p];
          }
          return t;
        };
        __rest2 = function(s, e) {
          var t = {};
          for (var p in s)
            if (Object.prototype.hasOwnProperty.call(s, p) && e.indexOf(p) < 0)
              t[p] = s[p];
          if (s != null && typeof Object.getOwnPropertySymbols === "function")
            for (var i = 0, p = Object.getOwnPropertySymbols(s); i < p.length; i++) {
              if (e.indexOf(p[i]) < 0 && Object.prototype.propertyIsEnumerable.call(s, p[i]))
                t[p[i]] = s[p[i]];
            }
          return t;
        };
        __decorate2 = function(decorators, target, key, desc) {
          var c = arguments.length, r = c < 3 ? target : desc === null ? desc = Object.getOwnPropertyDescriptor(target, key) : desc, d;
          if (typeof Reflect === "object" && typeof Reflect.decorate === "function")
            r = Reflect.decorate(decorators, target, key, desc);
          else
            for (var i = decorators.length - 1; i >= 0; i--)
              if (d = decorators[i])
                r = (c < 3 ? d(r) : c > 3 ? d(target, key, r) : d(target, key)) || r;
          return c > 3 && r && Object.defineProperty(target, key, r), r;
        };
        __param2 = function(paramIndex, decorator) {
          return function(target, key) {
            decorator(target, key, paramIndex);
          };
        };
        __metadata2 = function(metadataKey, metadataValue) {
          if (typeof Reflect === "object" && typeof Reflect.metadata === "function")
            return Reflect.metadata(metadataKey, metadataValue);
        };
        __awaiter3 = function(thisArg, _arguments, P, generator) {
          function adopt(value) {
            return value instanceof P ? value : new P(function(resolve) {
              resolve(value);
            });
          }
          return new (P || (P = Promise))(function(resolve, reject) {
            function fulfilled(value) {
              try {
                step(generator.next(value));
              } catch (e) {
                reject(e);
              }
            }
            function rejected(value) {
              try {
                step(generator["throw"](value));
              } catch (e) {
                reject(e);
              }
            }
            function step(result) {
              result.done ? resolve(result.value) : adopt(result.value).then(fulfilled, rejected);
            }
            step((generator = generator.apply(thisArg, _arguments || [])).next());
          });
        };
        __generator3 = function(thisArg, body) {
          var _ = { label: 0, sent: function() {
            if (t[0] & 1)
              throw t[1];
            return t[1];
          }, trys: [], ops: [] }, f, y, t, g;
          return g = { next: verb(0), "throw": verb(1), "return": verb(2) }, typeof Symbol === "function" && (g[Symbol.iterator] = function() {
            return this;
          }), g;
          function verb(n) {
            return function(v) {
              return step([n, v]);
            };
          }
          function step(op) {
            if (f)
              throw new TypeError("Generator is already executing.");
            while (_)
              try {
                if (f = 1, y && (t = op[0] & 2 ? y["return"] : op[0] ? y["throw"] || ((t = y["return"]) && t.call(y), 0) : y.next) && !(t = t.call(y, op[1])).done)
                  return t;
                if (y = 0, t)
                  op = [op[0] & 2, t.value];
                switch (op[0]) {
                  case 0:
                  case 1:
                    t = op;
                    break;
                  case 4:
                    _.label++;
                    return { value: op[1], done: false };
                  case 5:
                    _.label++;
                    y = op[1];
                    op = [0];
                    continue;
                  case 7:
                    op = _.ops.pop();
                    _.trys.pop();
                    continue;
                  default:
                    if (!(t = _.trys, t = t.length > 0 && t[t.length - 1]) && (op[0] === 6 || op[0] === 2)) {
                      _ = 0;
                      continue;
                    }
                    if (op[0] === 3 && (!t || op[1] > t[0] && op[1] < t[3])) {
                      _.label = op[1];
                      break;
                    }
                    if (op[0] === 6 && _.label < t[1]) {
                      _.label = t[1];
                      t = op;
                      break;
                    }
                    if (t && _.label < t[2]) {
                      _.label = t[2];
                      _.ops.push(op);
                      break;
                    }
                    if (t[2])
                      _.ops.pop();
                    _.trys.pop();
                    continue;
                }
                op = body.call(thisArg, _);
              } catch (e) {
                op = [6, e];
                y = 0;
              } finally {
                f = t = 0;
              }
            if (op[0] & 5)
              throw op[1];
            return { value: op[0] ? op[1] : void 0, done: true };
          }
        };
        __createBinding2 = function(o, m, k, k2) {
          if (k2 === void 0)
            k2 = k;
          o[k2] = m[k];
        };
        __exportStar2 = function(m, exports2) {
          for (var p in m)
            if (p !== "default" && !exports2.hasOwnProperty(p))
              exports2[p] = m[p];
        };
        __values3 = function(o) {
          var s = typeof Symbol === "function" && Symbol.iterator, m = s && o[s], i = 0;
          if (m)
            return m.call(o);
          if (o && typeof o.length === "number")
            return {
              next: function() {
                if (o && i >= o.length)
                  o = void 0;
                return { value: o && o[i++], done: !o };
              }
            };
          throw new TypeError(s ? "Object is not iterable." : "Symbol.iterator is not defined.");
        };
        __read2 = function(o, n) {
          var m = typeof Symbol === "function" && o[Symbol.iterator];
          if (!m)
            return o;
          var i = m.call(o), r, ar = [], e;
          try {
            while ((n === void 0 || n-- > 0) && !(r = i.next()).done)
              ar.push(r.value);
          } catch (error) {
            e = { error };
          } finally {
            try {
              if (r && !r.done && (m = i["return"]))
                m.call(i);
            } finally {
              if (e)
                throw e.error;
            }
          }
          return ar;
        };
        __spread2 = function() {
          for (var ar = [], i = 0; i < arguments.length; i++)
            ar = ar.concat(__read2(arguments[i]));
          return ar;
        };
        __spreadArrays2 = function() {
          for (var s = 0, i = 0, il = arguments.length; i < il; i++)
            s += arguments[i].length;
          for (var r = Array(s), k = 0, i = 0; i < il; i++)
            for (var a = arguments[i], j = 0, jl = a.length; j < jl; j++, k++)
              r[k] = a[j];
          return r;
        };
        __await2 = function(v) {
          return this instanceof __await2 ? (this.v = v, this) : new __await2(v);
        };
        __asyncGenerator2 = function(thisArg, _arguments, generator) {
          if (!Symbol.asyncIterator)
            throw new TypeError("Symbol.asyncIterator is not defined.");
          var g = generator.apply(thisArg, _arguments || []), i, q = [];
          return i = {}, verb("next"), verb("throw"), verb("return"), i[Symbol.asyncIterator] = function() {
            return this;
          }, i;
          function verb(n) {
            if (g[n])
              i[n] = function(v) {
                return new Promise(function(a, b) {
                  q.push([n, v, a, b]) > 1 || resume(n, v);
                });
              };
          }
          function resume(n, v) {
            try {
              step(g[n](v));
            } catch (e) {
              settle(q[0][3], e);
            }
          }
          function step(r) {
            r.value instanceof __await2 ? Promise.resolve(r.value.v).then(fulfill, reject) : settle(q[0][2], r);
          }
          function fulfill(value) {
            resume("next", value);
          }
          function reject(value) {
            resume("throw", value);
          }
          function settle(f, v) {
            if (f(v), q.shift(), q.length)
              resume(q[0][0], q[0][1]);
          }
        };
        __asyncDelegator2 = function(o) {
          var i, p;
          return i = {}, verb("next"), verb("throw", function(e) {
            throw e;
          }), verb("return"), i[Symbol.iterator] = function() {
            return this;
          }, i;
          function verb(n, f) {
            i[n] = o[n] ? function(v) {
              return (p = !p) ? { value: __await2(o[n](v)), done: n === "return" } : f ? f(v) : v;
            } : f;
          }
        };
        __asyncValues3 = function(o) {
          if (!Symbol.asyncIterator)
            throw new TypeError("Symbol.asyncIterator is not defined.");
          var m = o[Symbol.asyncIterator], i;
          return m ? m.call(o) : (o = typeof __values3 === "function" ? __values3(o) : o[Symbol.iterator](), i = {}, verb("next"), verb("throw"), verb("return"), i[Symbol.asyncIterator] = function() {
            return this;
          }, i);
          function verb(n) {
            i[n] = o[n] && function(v) {
              return new Promise(function(resolve, reject) {
                v = o[n](v), settle(resolve, reject, v.done, v.value);
              });
            };
          }
          function settle(resolve, reject, d, v) {
            Promise.resolve(v).then(function(v2) {
              resolve({ value: v2, done: d });
            }, reject);
          }
        };
        __makeTemplateObject2 = function(cooked, raw) {
          if (Object.defineProperty) {
            Object.defineProperty(cooked, "raw", { value: raw });
          } else {
            cooked.raw = raw;
          }
          return cooked;
        };
        __importStar2 = function(mod) {
          if (mod && mod.__esModule)
            return mod;
          var result = {};
          if (mod != null) {
            for (var k in mod)
              if (Object.hasOwnProperty.call(mod, k))
                result[k] = mod[k];
          }
          result["default"] = mod;
          return result;
        };
        __importDefault2 = function(mod) {
          return mod && mod.__esModule ? mod : { "default": mod };
        };
        __classPrivateFieldGet2 = function(receiver, privateMap) {
          if (!privateMap.has(receiver)) {
            throw new TypeError("attempted to get private field on non-instance");
          }
          return privateMap.get(receiver);
        };
        __classPrivateFieldSet2 = function(receiver, privateMap, value) {
          if (!privateMap.has(receiver)) {
            throw new TypeError("attempted to set private field on non-instance");
          }
          privateMap.set(receiver, value);
          return value;
        };
        exporter("__extends", __extends3);
        exporter("__assign", __assign3);
        exporter("__rest", __rest2);
        exporter("__decorate", __decorate2);
        exporter("__param", __param2);
        exporter("__metadata", __metadata2);
        exporter("__awaiter", __awaiter3);
        exporter("__generator", __generator3);
        exporter("__exportStar", __exportStar2);
        exporter("__createBinding", __createBinding2);
        exporter("__values", __values3);
        exporter("__read", __read2);
        exporter("__spread", __spread2);
        exporter("__spreadArrays", __spreadArrays2);
        exporter("__await", __await2);
        exporter("__asyncGenerator", __asyncGenerator2);
        exporter("__asyncDelegator", __asyncDelegator2);
        exporter("__asyncValues", __asyncValues3);
        exporter("__makeTemplateObject", __makeTemplateObject2);
        exporter("__importStar", __importStar2);
        exporter("__importDefault", __importDefault2);
        exporter("__classPrivateFieldGet", __classPrivateFieldGet2);
        exporter("__classPrivateFieldSet", __classPrivateFieldSet2);
      });
    }
  });

  // node_modules/reflect-metadata/Reflect.js
  var Reflect2;
  (function(Reflect3) {
    (function(factory) {
      var root = typeof global === "object" ? global : typeof self === "object" ? self : typeof this === "object" ? this : Function("return this;")();
      var exporter = makeExporter(Reflect3);
      if (typeof root.Reflect === "undefined") {
        root.Reflect = Reflect3;
      } else {
        exporter = makeExporter(root.Reflect, exporter);
      }
      factory(exporter);
      function makeExporter(target, previous) {
        return function(key, value) {
          if (typeof target[key] !== "function") {
            Object.defineProperty(target, key, { configurable: true, writable: true, value });
          }
          if (previous)
            previous(key, value);
        };
      }
    })(function(exporter) {
      var hasOwn = Object.prototype.hasOwnProperty;
      var supportsSymbol = typeof Symbol === "function";
      var toPrimitiveSymbol = supportsSymbol && typeof Symbol.toPrimitive !== "undefined" ? Symbol.toPrimitive : "@@toPrimitive";
      var iteratorSymbol = supportsSymbol && typeof Symbol.iterator !== "undefined" ? Symbol.iterator : "@@iterator";
      var supportsCreate = typeof Object.create === "function";
      var supportsProto = { __proto__: [] } instanceof Array;
      var downLevel = !supportsCreate && !supportsProto;
      var HashMap = {
        create: supportsCreate ? function() {
          return MakeDictionary(/* @__PURE__ */ Object.create(null));
        } : supportsProto ? function() {
          return MakeDictionary({ __proto__: null });
        } : function() {
          return MakeDictionary({});
        },
        has: downLevel ? function(map, key) {
          return hasOwn.call(map, key);
        } : function(map, key) {
          return key in map;
        },
        get: downLevel ? function(map, key) {
          return hasOwn.call(map, key) ? map[key] : void 0;
        } : function(map, key) {
          return map[key];
        }
      };
      var functionPrototype = Object.getPrototypeOf(Function);
      var usePolyfill = typeof process === "object" && process.env && process.env["REFLECT_METADATA_USE_MAP_POLYFILL"] === "true";
      var _Map = !usePolyfill && typeof Map === "function" && typeof Map.prototype.entries === "function" ? Map : CreateMapPolyfill();
      var _Set = !usePolyfill && typeof Set === "function" && typeof Set.prototype.entries === "function" ? Set : CreateSetPolyfill();
      var _WeakMap = !usePolyfill && typeof WeakMap === "function" ? WeakMap : CreateWeakMapPolyfill();
      var Metadata = new _WeakMap();
      function decorate(decorators, target, propertyKey, attributes) {
        if (!IsUndefined(propertyKey)) {
          if (!IsArray(decorators))
            throw new TypeError();
          if (!IsObject(target))
            throw new TypeError();
          if (!IsObject(attributes) && !IsUndefined(attributes) && !IsNull(attributes))
            throw new TypeError();
          if (IsNull(attributes))
            attributes = void 0;
          propertyKey = ToPropertyKey(propertyKey);
          return DecorateProperty(decorators, target, propertyKey, attributes);
        } else {
          if (!IsArray(decorators))
            throw new TypeError();
          if (!IsConstructor(target))
            throw new TypeError();
          return DecorateConstructor(decorators, target);
        }
      }
      exporter("decorate", decorate);
      function metadata(metadataKey, metadataValue) {
        function decorator(target, propertyKey) {
          if (!IsObject(target))
            throw new TypeError();
          if (!IsUndefined(propertyKey) && !IsPropertyKey(propertyKey))
            throw new TypeError();
          OrdinaryDefineOwnMetadata(metadataKey, metadataValue, target, propertyKey);
        }
        return decorator;
      }
      exporter("metadata", metadata);
      function defineMetadata(metadataKey, metadataValue, target, propertyKey) {
        if (!IsObject(target))
          throw new TypeError();
        if (!IsUndefined(propertyKey))
          propertyKey = ToPropertyKey(propertyKey);
        return OrdinaryDefineOwnMetadata(metadataKey, metadataValue, target, propertyKey);
      }
      exporter("defineMetadata", defineMetadata);
      function hasMetadata(metadataKey, target, propertyKey) {
        if (!IsObject(target))
          throw new TypeError();
        if (!IsUndefined(propertyKey))
          propertyKey = ToPropertyKey(propertyKey);
        return OrdinaryHasMetadata(metadataKey, target, propertyKey);
      }
      exporter("hasMetadata", hasMetadata);
      function hasOwnMetadata(metadataKey, target, propertyKey) {
        if (!IsObject(target))
          throw new TypeError();
        if (!IsUndefined(propertyKey))
          propertyKey = ToPropertyKey(propertyKey);
        return OrdinaryHasOwnMetadata(metadataKey, target, propertyKey);
      }
      exporter("hasOwnMetadata", hasOwnMetadata);
      function getMetadata(metadataKey, target, propertyKey) {
        if (!IsObject(target))
          throw new TypeError();
        if (!IsUndefined(propertyKey))
          propertyKey = ToPropertyKey(propertyKey);
        return OrdinaryGetMetadata(metadataKey, target, propertyKey);
      }
      exporter("getMetadata", getMetadata);
      function getOwnMetadata(metadataKey, target, propertyKey) {
        if (!IsObject(target))
          throw new TypeError();
        if (!IsUndefined(propertyKey))
          propertyKey = ToPropertyKey(propertyKey);
        return OrdinaryGetOwnMetadata(metadataKey, target, propertyKey);
      }
      exporter("getOwnMetadata", getOwnMetadata);
      function getMetadataKeys(target, propertyKey) {
        if (!IsObject(target))
          throw new TypeError();
        if (!IsUndefined(propertyKey))
          propertyKey = ToPropertyKey(propertyKey);
        return OrdinaryMetadataKeys(target, propertyKey);
      }
      exporter("getMetadataKeys", getMetadataKeys);
      function getOwnMetadataKeys(target, propertyKey) {
        if (!IsObject(target))
          throw new TypeError();
        if (!IsUndefined(propertyKey))
          propertyKey = ToPropertyKey(propertyKey);
        return OrdinaryOwnMetadataKeys(target, propertyKey);
      }
      exporter("getOwnMetadataKeys", getOwnMetadataKeys);
      function deleteMetadata(metadataKey, target, propertyKey) {
        if (!IsObject(target))
          throw new TypeError();
        if (!IsUndefined(propertyKey))
          propertyKey = ToPropertyKey(propertyKey);
        var metadataMap = GetOrCreateMetadataMap(target, propertyKey, false);
        if (IsUndefined(metadataMap))
          return false;
        if (!metadataMap.delete(metadataKey))
          return false;
        if (metadataMap.size > 0)
          return true;
        var targetMetadata = Metadata.get(target);
        targetMetadata.delete(propertyKey);
        if (targetMetadata.size > 0)
          return true;
        Metadata.delete(target);
        return true;
      }
      exporter("deleteMetadata", deleteMetadata);
      function DecorateConstructor(decorators, target) {
        for (var i = decorators.length - 1; i >= 0; --i) {
          var decorator = decorators[i];
          var decorated = decorator(target);
          if (!IsUndefined(decorated) && !IsNull(decorated)) {
            if (!IsConstructor(decorated))
              throw new TypeError();
            target = decorated;
          }
        }
        return target;
      }
      function DecorateProperty(decorators, target, propertyKey, descriptor) {
        for (var i = decorators.length - 1; i >= 0; --i) {
          var decorator = decorators[i];
          var decorated = decorator(target, propertyKey, descriptor);
          if (!IsUndefined(decorated) && !IsNull(decorated)) {
            if (!IsObject(decorated))
              throw new TypeError();
            descriptor = decorated;
          }
        }
        return descriptor;
      }
      function GetOrCreateMetadataMap(O, P, Create) {
        var targetMetadata = Metadata.get(O);
        if (IsUndefined(targetMetadata)) {
          if (!Create)
            return void 0;
          targetMetadata = new _Map();
          Metadata.set(O, targetMetadata);
        }
        var metadataMap = targetMetadata.get(P);
        if (IsUndefined(metadataMap)) {
          if (!Create)
            return void 0;
          metadataMap = new _Map();
          targetMetadata.set(P, metadataMap);
        }
        return metadataMap;
      }
      function OrdinaryHasMetadata(MetadataKey, O, P) {
        var hasOwn2 = OrdinaryHasOwnMetadata(MetadataKey, O, P);
        if (hasOwn2)
          return true;
        var parent = OrdinaryGetPrototypeOf(O);
        if (!IsNull(parent))
          return OrdinaryHasMetadata(MetadataKey, parent, P);
        return false;
      }
      function OrdinaryHasOwnMetadata(MetadataKey, O, P) {
        var metadataMap = GetOrCreateMetadataMap(O, P, false);
        if (IsUndefined(metadataMap))
          return false;
        return ToBoolean(metadataMap.has(MetadataKey));
      }
      function OrdinaryGetMetadata(MetadataKey, O, P) {
        var hasOwn2 = OrdinaryHasOwnMetadata(MetadataKey, O, P);
        if (hasOwn2)
          return OrdinaryGetOwnMetadata(MetadataKey, O, P);
        var parent = OrdinaryGetPrototypeOf(O);
        if (!IsNull(parent))
          return OrdinaryGetMetadata(MetadataKey, parent, P);
        return void 0;
      }
      function OrdinaryGetOwnMetadata(MetadataKey, O, P) {
        var metadataMap = GetOrCreateMetadataMap(O, P, false);
        if (IsUndefined(metadataMap))
          return void 0;
        return metadataMap.get(MetadataKey);
      }
      function OrdinaryDefineOwnMetadata(MetadataKey, MetadataValue, O, P) {
        var metadataMap = GetOrCreateMetadataMap(O, P, true);
        metadataMap.set(MetadataKey, MetadataValue);
      }
      function OrdinaryMetadataKeys(O, P) {
        var ownKeys = OrdinaryOwnMetadataKeys(O, P);
        var parent = OrdinaryGetPrototypeOf(O);
        if (parent === null)
          return ownKeys;
        var parentKeys = OrdinaryMetadataKeys(parent, P);
        if (parentKeys.length <= 0)
          return ownKeys;
        if (ownKeys.length <= 0)
          return parentKeys;
        var set = new _Set();
        var keys = [];
        for (var _i = 0, ownKeys_1 = ownKeys; _i < ownKeys_1.length; _i++) {
          var key = ownKeys_1[_i];
          var hasKey = set.has(key);
          if (!hasKey) {
            set.add(key);
            keys.push(key);
          }
        }
        for (var _a = 0, parentKeys_1 = parentKeys; _a < parentKeys_1.length; _a++) {
          var key = parentKeys_1[_a];
          var hasKey = set.has(key);
          if (!hasKey) {
            set.add(key);
            keys.push(key);
          }
        }
        return keys;
      }
      function OrdinaryOwnMetadataKeys(O, P) {
        var keys = [];
        var metadataMap = GetOrCreateMetadataMap(O, P, false);
        if (IsUndefined(metadataMap))
          return keys;
        var keysObj = metadataMap.keys();
        var iterator = GetIterator(keysObj);
        var k = 0;
        while (true) {
          var next = IteratorStep(iterator);
          if (!next) {
            keys.length = k;
            return keys;
          }
          var nextValue = IteratorValue(next);
          try {
            keys[k] = nextValue;
          } catch (e) {
            try {
              IteratorClose(iterator);
            } finally {
              throw e;
            }
          }
          k++;
        }
      }
      function Type(x) {
        if (x === null)
          return 1;
        switch (typeof x) {
          case "undefined":
            return 0;
          case "boolean":
            return 2;
          case "string":
            return 3;
          case "symbol":
            return 4;
          case "number":
            return 5;
          case "object":
            return x === null ? 1 : 6;
          default:
            return 6;
        }
      }
      function IsUndefined(x) {
        return x === void 0;
      }
      function IsNull(x) {
        return x === null;
      }
      function IsSymbol(x) {
        return typeof x === "symbol";
      }
      function IsObject(x) {
        return typeof x === "object" ? x !== null : typeof x === "function";
      }
      function ToPrimitive(input, PreferredType) {
        switch (Type(input)) {
          case 0:
            return input;
          case 1:
            return input;
          case 2:
            return input;
          case 3:
            return input;
          case 4:
            return input;
          case 5:
            return input;
        }
        var hint = PreferredType === 3 ? "string" : PreferredType === 5 ? "number" : "default";
        var exoticToPrim = GetMethod(input, toPrimitiveSymbol);
        if (exoticToPrim !== void 0) {
          var result = exoticToPrim.call(input, hint);
          if (IsObject(result))
            throw new TypeError();
          return result;
        }
        return OrdinaryToPrimitive(input, hint === "default" ? "number" : hint);
      }
      function OrdinaryToPrimitive(O, hint) {
        if (hint === "string") {
          var toString_1 = O.toString;
          if (IsCallable(toString_1)) {
            var result = toString_1.call(O);
            if (!IsObject(result))
              return result;
          }
          var valueOf = O.valueOf;
          if (IsCallable(valueOf)) {
            var result = valueOf.call(O);
            if (!IsObject(result))
              return result;
          }
        } else {
          var valueOf = O.valueOf;
          if (IsCallable(valueOf)) {
            var result = valueOf.call(O);
            if (!IsObject(result))
              return result;
          }
          var toString_2 = O.toString;
          if (IsCallable(toString_2)) {
            var result = toString_2.call(O);
            if (!IsObject(result))
              return result;
          }
        }
        throw new TypeError();
      }
      function ToBoolean(argument) {
        return !!argument;
      }
      function ToString(argument) {
        return "" + argument;
      }
      function ToPropertyKey(argument) {
        var key = ToPrimitive(argument, 3);
        if (IsSymbol(key))
          return key;
        return ToString(key);
      }
      function IsArray(argument) {
        return Array.isArray ? Array.isArray(argument) : argument instanceof Object ? argument instanceof Array : Object.prototype.toString.call(argument) === "[object Array]";
      }
      function IsCallable(argument) {
        return typeof argument === "function";
      }
      function IsConstructor(argument) {
        return typeof argument === "function";
      }
      function IsPropertyKey(argument) {
        switch (Type(argument)) {
          case 3:
            return true;
          case 4:
            return true;
          default:
            return false;
        }
      }
      function GetMethod(V, P) {
        var func = V[P];
        if (func === void 0 || func === null)
          return void 0;
        if (!IsCallable(func))
          throw new TypeError();
        return func;
      }
      function GetIterator(obj) {
        var method = GetMethod(obj, iteratorSymbol);
        if (!IsCallable(method))
          throw new TypeError();
        var iterator = method.call(obj);
        if (!IsObject(iterator))
          throw new TypeError();
        return iterator;
      }
      function IteratorValue(iterResult) {
        return iterResult.value;
      }
      function IteratorStep(iterator) {
        var result = iterator.next();
        return result.done ? false : result;
      }
      function IteratorClose(iterator) {
        var f = iterator["return"];
        if (f)
          f.call(iterator);
      }
      function OrdinaryGetPrototypeOf(O) {
        var proto = Object.getPrototypeOf(O);
        if (typeof O !== "function" || O === functionPrototype)
          return proto;
        if (proto !== functionPrototype)
          return proto;
        var prototype = O.prototype;
        var prototypeProto = prototype && Object.getPrototypeOf(prototype);
        if (prototypeProto == null || prototypeProto === Object.prototype)
          return proto;
        var constructor = prototypeProto.constructor;
        if (typeof constructor !== "function")
          return proto;
        if (constructor === O)
          return proto;
        return constructor;
      }
      function CreateMapPolyfill() {
        var cacheSentinel = {};
        var arraySentinel = [];
        var MapIterator = function() {
          function MapIterator2(keys, values, selector) {
            this._index = 0;
            this._keys = keys;
            this._values = values;
            this._selector = selector;
          }
          MapIterator2.prototype["@@iterator"] = function() {
            return this;
          };
          MapIterator2.prototype[iteratorSymbol] = function() {
            return this;
          };
          MapIterator2.prototype.next = function() {
            var index = this._index;
            if (index >= 0 && index < this._keys.length) {
              var result = this._selector(this._keys[index], this._values[index]);
              if (index + 1 >= this._keys.length) {
                this._index = -1;
                this._keys = arraySentinel;
                this._values = arraySentinel;
              } else {
                this._index++;
              }
              return { value: result, done: false };
            }
            return { value: void 0, done: true };
          };
          MapIterator2.prototype.throw = function(error) {
            if (this._index >= 0) {
              this._index = -1;
              this._keys = arraySentinel;
              this._values = arraySentinel;
            }
            throw error;
          };
          MapIterator2.prototype.return = function(value) {
            if (this._index >= 0) {
              this._index = -1;
              this._keys = arraySentinel;
              this._values = arraySentinel;
            }
            return { value, done: true };
          };
          return MapIterator2;
        }();
        return function() {
          function Map2() {
            this._keys = [];
            this._values = [];
            this._cacheKey = cacheSentinel;
            this._cacheIndex = -2;
          }
          Object.defineProperty(Map2.prototype, "size", {
            get: function() {
              return this._keys.length;
            },
            enumerable: true,
            configurable: true
          });
          Map2.prototype.has = function(key) {
            return this._find(key, false) >= 0;
          };
          Map2.prototype.get = function(key) {
            var index = this._find(key, false);
            return index >= 0 ? this._values[index] : void 0;
          };
          Map2.prototype.set = function(key, value) {
            var index = this._find(key, true);
            this._values[index] = value;
            return this;
          };
          Map2.prototype.delete = function(key) {
            var index = this._find(key, false);
            if (index >= 0) {
              var size = this._keys.length;
              for (var i = index + 1; i < size; i++) {
                this._keys[i - 1] = this._keys[i];
                this._values[i - 1] = this._values[i];
              }
              this._keys.length--;
              this._values.length--;
              if (key === this._cacheKey) {
                this._cacheKey = cacheSentinel;
                this._cacheIndex = -2;
              }
              return true;
            }
            return false;
          };
          Map2.prototype.clear = function() {
            this._keys.length = 0;
            this._values.length = 0;
            this._cacheKey = cacheSentinel;
            this._cacheIndex = -2;
          };
          Map2.prototype.keys = function() {
            return new MapIterator(this._keys, this._values, getKey);
          };
          Map2.prototype.values = function() {
            return new MapIterator(this._keys, this._values, getValue);
          };
          Map2.prototype.entries = function() {
            return new MapIterator(this._keys, this._values, getEntry);
          };
          Map2.prototype["@@iterator"] = function() {
            return this.entries();
          };
          Map2.prototype[iteratorSymbol] = function() {
            return this.entries();
          };
          Map2.prototype._find = function(key, insert) {
            if (this._cacheKey !== key) {
              this._cacheIndex = this._keys.indexOf(this._cacheKey = key);
            }
            if (this._cacheIndex < 0 && insert) {
              this._cacheIndex = this._keys.length;
              this._keys.push(key);
              this._values.push(void 0);
            }
            return this._cacheIndex;
          };
          return Map2;
        }();
        function getKey(key, _) {
          return key;
        }
        function getValue(_, value) {
          return value;
        }
        function getEntry(key, value) {
          return [key, value];
        }
      }
      function CreateSetPolyfill() {
        return function() {
          function Set2() {
            this._map = new _Map();
          }
          Object.defineProperty(Set2.prototype, "size", {
            get: function() {
              return this._map.size;
            },
            enumerable: true,
            configurable: true
          });
          Set2.prototype.has = function(value) {
            return this._map.has(value);
          };
          Set2.prototype.add = function(value) {
            return this._map.set(value, value), this;
          };
          Set2.prototype.delete = function(value) {
            return this._map.delete(value);
          };
          Set2.prototype.clear = function() {
            this._map.clear();
          };
          Set2.prototype.keys = function() {
            return this._map.keys();
          };
          Set2.prototype.values = function() {
            return this._map.values();
          };
          Set2.prototype.entries = function() {
            return this._map.entries();
          };
          Set2.prototype["@@iterator"] = function() {
            return this.keys();
          };
          Set2.prototype[iteratorSymbol] = function() {
            return this.keys();
          };
          return Set2;
        }();
      }
      function CreateWeakMapPolyfill() {
        var UUID_SIZE = 16;
        var keys = HashMap.create();
        var rootKey = CreateUniqueKey();
        return function() {
          function WeakMap2() {
            this._key = CreateUniqueKey();
          }
          WeakMap2.prototype.has = function(target) {
            var table = GetOrCreateWeakMapTable(target, false);
            return table !== void 0 ? HashMap.has(table, this._key) : false;
          };
          WeakMap2.prototype.get = function(target) {
            var table = GetOrCreateWeakMapTable(target, false);
            return table !== void 0 ? HashMap.get(table, this._key) : void 0;
          };
          WeakMap2.prototype.set = function(target, value) {
            var table = GetOrCreateWeakMapTable(target, true);
            table[this._key] = value;
            return this;
          };
          WeakMap2.prototype.delete = function(target) {
            var table = GetOrCreateWeakMapTable(target, false);
            return table !== void 0 ? delete table[this._key] : false;
          };
          WeakMap2.prototype.clear = function() {
            this._key = CreateUniqueKey();
          };
          return WeakMap2;
        }();
        function CreateUniqueKey() {
          var key;
          do
            key = "@@WeakMap@@" + CreateUUID();
          while (HashMap.has(keys, key));
          keys[key] = true;
          return key;
        }
        function GetOrCreateWeakMapTable(target, create) {
          if (!hasOwn.call(target, rootKey)) {
            if (!create)
              return void 0;
            Object.defineProperty(target, rootKey, { value: HashMap.create() });
          }
          return target[rootKey];
        }
        function FillRandomBytes(buffer, size) {
          for (var i = 0; i < size; ++i)
            buffer[i] = Math.random() * 255 | 0;
          return buffer;
        }
        function GenRandomBytes(size) {
          if (typeof Uint8Array === "function") {
            if (typeof crypto !== "undefined")
              return crypto.getRandomValues(new Uint8Array(size));
            if (typeof msCrypto !== "undefined")
              return msCrypto.getRandomValues(new Uint8Array(size));
            return FillRandomBytes(new Uint8Array(size), size);
          }
          return FillRandomBytes(new Array(size), size);
        }
        function CreateUUID() {
          var data = GenRandomBytes(UUID_SIZE);
          data[6] = data[6] & 79 | 64;
          data[8] = data[8] & 191 | 128;
          var result = "";
          for (var offset = 0; offset < UUID_SIZE; ++offset) {
            var byte = data[offset];
            if (offset === 4 || offset === 6 || offset === 8)
              result += "-";
            if (byte < 16)
              result += "0";
            result += byte.toString(16).toLowerCase();
          }
          return result;
        }
      }
      function MakeDictionary(obj) {
        obj.__ = void 0;
        delete obj.__;
        return obj;
      }
    });
  })(Reflect2 || (Reflect2 = {}));

  // src/modules/cookieConsent/client/detectors/CookieDomWatcher.ts
  var CookieDomWatcher = class {
    constructor(detectionRules, timeout = 5 * 1e3) {
      this.detectionRules = detectionRules;
      this.config = { childList: true, subtree: true };
      this.promiseResolve = () => {
      };
      this.promiseReject = () => {
      };
      this.timer = setTimeout(this.onTimeout.bind(this), timeout);
    }
    observe() {
      return new Promise((resolve, reject) => {
        this.promiseResolve = resolve;
        this.promiseReject = reject;
        this.onDomChange();
        this.observer = new MutationObserver(() => this.onDomChange());
        this.observer.observe(document, this.config);
      });
    }
    onDomChange() {
      const scenario = this.getCookieData();
      if (!scenario)
        return;
      this.dispose();
      this.promiseResolve(scenario);
    }
    getCookieData() {
      for (let i = 0; i < this.detectionRules.length; i++) {
        const variant = this.processDetectors(this.detectionRules[i].detectors);
        if (!variant)
          continue;
        return { scenario: this.detectionRules[i].type, variant };
      }
    }
    processDetectors(detectors) {
      if (!detectors || !detectors.length)
        return;
      for (let i = 0; i < detectors.length; i++) {
        const element = this.checkSelectors(detectors[i].selectors);
        if (element)
          return detectors[i].variant;
      }
    }
    checkSelectors(selectors) {
      if (!selectors)
        return;
      for (let i = 0; i < selectors.length; i++) {
        const element = this.getElement(selectors[i]);
        if (element)
          return element;
      }
    }
    getElement(selector) {
      const char = selector.charAt(0);
      switch (char) {
        case "#":
          return document.getElementById(selector.slice(1, selector.length));
        case ".":
          return document.getElementsByClassName(selector.slice(1, selector.length))[0];
        default:
          return document.querySelector(selector);
      }
    }
    dispose() {
      this.disposeObserver();
      this.clearTimer();
    }
    clearTimer() {
      if (this.timer)
        clearTimeout(this.timer);
      this.timer = void 0;
    }
    onTimeout() {
      this.dispose();
      this.promiseReject();
    }
    disposeObserver() {
      if (!this.observer)
        return;
      this.observer.disconnect();
      this.observer = void 0;
    }
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

  // src/modules/cookieConsent/client/script/handler/CookieHandlerBase.ts
  var CookieHandlerBase = class {
    getScenario(scenarioParams) {
      return new ClientMessageQuery("cookieManager.getScenario" /* GET_SCENARIO */, { scenarioParams }).execute();
    }
  };

  // node_modules/@avast/scenarios-runner/lib/index.es.js
  var extendStatics = function(d, b) {
    extendStatics = Object.setPrototypeOf || { __proto__: [] } instanceof Array && function(d2, b2) {
      d2.__proto__ = b2;
    } || function(d2, b2) {
      for (var p in b2)
        if (Object.prototype.hasOwnProperty.call(b2, p))
          d2[p] = b2[p];
    };
    return extendStatics(d, b);
  };
  function __extends(d, b) {
    if (typeof b !== "function" && b !== null)
      throw new TypeError("Class extends value " + String(b) + " is not a constructor or null");
    extendStatics(d, b);
    function __() {
      this.constructor = d;
    }
    d.prototype = b === null ? Object.create(b) : (__.prototype = b.prototype, new __());
  }
  var __assign = function() {
    __assign = Object.assign || function __assign3(t) {
      for (var s, i = 1, n = arguments.length; i < n; i++) {
        s = arguments[i];
        for (var p in s)
          if (Object.prototype.hasOwnProperty.call(s, p))
            t[p] = s[p];
      }
      return t;
    };
    return __assign.apply(this, arguments);
  };
  function __awaiter(thisArg, _arguments, P, generator) {
    function adopt(value) {
      return value instanceof P ? value : new P(function(resolve) {
        resolve(value);
      });
    }
    return new (P || (P = Promise))(function(resolve, reject) {
      function fulfilled(value) {
        try {
          step(generator.next(value));
        } catch (e) {
          reject(e);
        }
      }
      function rejected(value) {
        try {
          step(generator["throw"](value));
        } catch (e) {
          reject(e);
        }
      }
      function step(result) {
        result.done ? resolve(result.value) : adopt(result.value).then(fulfilled, rejected);
      }
      step((generator = generator.apply(thisArg, _arguments || [])).next());
    });
  }
  function __generator(thisArg, body) {
    var _ = { label: 0, sent: function() {
      if (t[0] & 1)
        throw t[1];
      return t[1];
    }, trys: [], ops: [] }, f, y, t, g;
    return g = { next: verb(0), "throw": verb(1), "return": verb(2) }, typeof Symbol === "function" && (g[Symbol.iterator] = function() {
      return this;
    }), g;
    function verb(n) {
      return function(v) {
        return step([n, v]);
      };
    }
    function step(op) {
      if (f)
        throw new TypeError("Generator is already executing.");
      while (_)
        try {
          if (f = 1, y && (t = op[0] & 2 ? y["return"] : op[0] ? y["throw"] || ((t = y["return"]) && t.call(y), 0) : y.next) && !(t = t.call(y, op[1])).done)
            return t;
          if (y = 0, t)
            op = [op[0] & 2, t.value];
          switch (op[0]) {
            case 0:
            case 1:
              t = op;
              break;
            case 4:
              _.label++;
              return { value: op[1], done: false };
            case 5:
              _.label++;
              y = op[1];
              op = [0];
              continue;
            case 7:
              op = _.ops.pop();
              _.trys.pop();
              continue;
            default:
              if (!(t = _.trys, t = t.length > 0 && t[t.length - 1]) && (op[0] === 6 || op[0] === 2)) {
                _ = 0;
                continue;
              }
              if (op[0] === 3 && (!t || op[1] > t[0] && op[1] < t[3])) {
                _.label = op[1];
                break;
              }
              if (op[0] === 6 && _.label < t[1]) {
                _.label = t[1];
                t = op;
                break;
              }
              if (t && _.label < t[2]) {
                _.label = t[2];
                _.ops.push(op);
                break;
              }
              if (t[2])
                _.ops.pop();
              _.trys.pop();
              continue;
          }
          op = body.call(thisArg, _);
        } catch (e) {
          op = [6, e];
          y = 0;
        } finally {
          f = t = 0;
        }
      if (op[0] & 5)
        throw op[1];
      return { value: op[0] ? op[1] : void 0, done: true };
    }
  }
  function __values(o) {
    var s = typeof Symbol === "function" && Symbol.iterator, m = s && o[s], i = 0;
    if (m)
      return m.call(o);
    if (o && typeof o.length === "number")
      return {
        next: function() {
          if (o && i >= o.length)
            o = void 0;
          return { value: o && o[i++], done: !o };
        }
      };
    throw new TypeError(s ? "Object is not iterable." : "Symbol.iterator is not defined.");
  }
  function __spreadArray(to, from, pack) {
    if (pack || arguments.length === 2)
      for (var i = 0, l = from.length, ar; i < l; i++) {
        if (ar || !(i in from)) {
          if (!ar)
            ar = Array.prototype.slice.call(from, 0, i);
          ar[i] = from[i];
        }
      }
    return to.concat(ar || Array.prototype.slice.call(from));
  }
  function __asyncValues(o) {
    if (!Symbol.asyncIterator)
      throw new TypeError("Symbol.asyncIterator is not defined.");
    var m = o[Symbol.asyncIterator], i;
    return m ? m.call(o) : (o = typeof __values === "function" ? __values(o) : o[Symbol.iterator](), i = {}, verb("next"), verb("throw"), verb("return"), i[Symbol.asyncIterator] = function() {
      return this;
    }, i);
    function verb(n) {
      i[n] = o[n] && function(v) {
        return new Promise(function(resolve, reject) {
          v = o[n](v), settle(resolve, reject, v.done, v.value);
        });
      };
    }
    function settle(resolve, reject, d, v) {
      Promise.resolve(v).then(function(v2) {
        resolve({ value: v2, done: d });
      }, reject);
    }
  }
  var PrivacyScenarioKeys;
  (function(PrivacyScenarioKeys2) {
    PrivacyScenarioKeys2["name"] = "name";
    PrivacyScenarioKeys2["pages"] = "pages";
  })(PrivacyScenarioKeys || (PrivacyScenarioKeys = {}));
  var PrivacyPageKeys;
  (function(PrivacyPageKeys2) {
    PrivacyPageKeys2["target"] = "target";
    PrivacyPageKeys2["actions"] = "actions";
    PrivacyPageKeys2["groupedActions"] = "groupedActions";
    PrivacyPageKeys2["hooks"] = "hooks";
  })(PrivacyPageKeys || (PrivacyPageKeys = {}));
  var HandledError = function(_super) {
    __extends(HandledError2, _super);
    function HandledError2() {
      var _newTarget = this.constructor;
      var _this = _super.call(this) || this;
      _this.name = _newTarget.name;
      _this.message = "Unexpected error occurred.";
      Object.setPrototypeOf(_this, _newTarget.prototype);
      return _this;
    }
    Object.defineProperty(HandledError2.prototype, "errorDetails", {
      get: function() {
        return void 0;
      },
      enumerable: false,
      configurable: true
    });
    return HandledError2;
  }(Error);
  var ParseActionsFormatError = function(_super) {
    __extends(ParseActionsFormatError2, _super);
    function ParseActionsFormatError2() {
      var _this = _super.call(this) || this;
      _this.message = 'Unable to parse the page - "actions" or "groupedActions" field is either missing or the value is not valid.';
      return _this;
    }
    return ParseActionsFormatError2;
  }(HandledError);
  var ParserInvalidActionsError = function(_super) {
    __extends(ParserInvalidActionsError2, _super);
    function ParserInvalidActionsError2(invalidActions) {
      var _this = _super.call(this) || this;
      _this.invalidActions = invalidActions;
      _this.message = 'Unable to parse following page actions: "'.concat(invalidActions.join(", "), '".');
      return _this;
    }
    return ParserInvalidActionsError2;
  }(HandledError);
  var ParserInvalidHooksError = function(_super) {
    __extends(ParserInvalidHooksError2, _super);
    function ParserInvalidHooksError2(invalidHooks) {
      var _this = _super.call(this) || this;
      _this.invalidHooks = invalidHooks;
      _this.message = 'Unable to parse following page actions: "'.concat(invalidHooks.join(", "), '".');
      return _this;
    }
    return ParserInvalidHooksError2;
  }(HandledError);
  var ParserInvalidPageTargetError = function(_super) {
    __extends(ParserInvalidPageTargetError2, _super);
    function ParserInvalidPageTargetError2() {
      var _this = _super.call(this) || this;
      _this.message = 'Unable to parse the page - "target" field is either missing or the value is not valid.';
      return _this;
    }
    return ParserInvalidPageTargetError2;
  }(HandledError);
  var HookType;
  (function(HookType2) {
    HookType2["onSuccess"] = "onSuccess";
    HookType2["onStop"] = "onStop";
    HookType2["onDisposed"] = "onDisposed";
    HookType2["onFailed"] = "onFailed";
  })(HookType || (HookType = {}));
  var ActionEvents;
  (function(ActionEvents5) {
    ActionEvents5["bulkClick"] = "bulkClick";
    ActionEvents5["clickOneOf"] = "clickOneOf";
    ActionEvents5["click"] = "click";
    ActionEvents5["clickWhenVisible"] = "clickWhenVisible";
    ActionEvents5["executeScript"] = "executeScript";
    ActionEvents5["injectStyles"] = "injectStyles";
    ActionEvents5["notification"] = "notification";
    ActionEvents5["scroll"] = "scroll";
    ActionEvents5["stopScenario"] = "stopScenario";
    ActionEvents5["tooltip"] = "tooltip";
    ActionEvents5["unknown"] = "unknown";
    ActionEvents5["verifyOk"] = "verifyOk";
    ActionEvents5["waitUntilVisible"] = "waitUntilVisible";
    ActionEvents5["waitUntilOneVisible"] = "waitUntilOneVisible";
    ActionEvents5["delay"] = "delay";
  })(ActionEvents || (ActionEvents = {}));
  var ActionExecutionError = function(_super) {
    __extends(ActionExecutionError2, _super);
    function ActionExecutionError2(event, failReason) {
      var _this = _super.call(this) || this;
      _this.event = event;
      _this.failReason = failReason;
      _this.message = 'Action "'.concat(_this.event, '" execution failed.');
      return _this;
    }
    Object.defineProperty(ActionExecutionError2.prototype, "errorDetails", {
      get: function() {
        return [{
          key: this.event,
          description: this.failReason.message,
          failReason: this.failReason
        }];
      },
      enumerable: false,
      configurable: true
    });
    return ActionExecutionError2;
  }(HandledError);
  var ActionResult = function() {
    function ActionResult3(resolution, nextGroup) {
      this.resolution = resolution;
      this.nextGroup = nextGroup;
    }
    return ActionResult3;
  }();
  var ParserError = function(_super) {
    __extends(ParserError2, _super);
    function ParserError2(scenarioName, invalidValues) {
      var _this = _super.call(this) || this;
      _this.scenarioName = scenarioName;
      _this.invalidValues = invalidValues;
      _this.message = "Parsing the ".concat(scenarioName, ' failed - "').concat(_this.getInvalidKeysString(), '" entries are invalid.');
      return _this;
    }
    Object.defineProperty(ParserError2.prototype, "errorDetails", {
      get: function() {
        return this.invalidValues;
      },
      enumerable: false,
      configurable: true
    });
    ParserError2.prototype.getInvalidKeysString = function() {
      return this.invalidValues.map(function(value) {
        return value.key;
      }).join(", ");
    };
    return ParserError2;
  }(HandledError);
  var ScenarioResult = function() {
    function ScenarioResult3(scenarioName, resolution, stack, error) {
      this.scenarioName = scenarioName;
      this.resolution = resolution;
      this.stack = stack;
      this.error = error;
    }
    ScenarioResult3.buildFailedResult = function(scenario, error, executionStack) {
      return new ScenarioResult3(this.resolveScenarioName(scenario, error), Resolution.failed, executionStack, this.getScenarioError(error));
    };
    ScenarioResult3.resolveScenarioName = function(scenario, error) {
      if (error instanceof ParserError)
        return error.scenarioName;
      return (scenario === null || scenario === void 0 ? void 0 : scenario.name) ? scenario.name : "Unknown";
    };
    ScenarioResult3.getScenarioError = function(error) {
      return {
        name: error.name,
        message: error.message,
        details: error.errorDetails
      };
    };
    return ScenarioResult3;
  }();
  var Resolution;
  (function(Resolution2) {
    Resolution2["failed"] = "failed";
    Resolution2["succeeded"] = "succeeded";
    Resolution2["stopped"] = "stopped";
    Resolution2["terminated"] = "terminated";
  })(Resolution || (Resolution = {}));
  var ActionBase = function() {
    function ActionBase2() {
    }
    ActionBase2.prototype.dispose = function() {
      for (var key in this)
        if (this.hasOwnProperty(key))
          delete this[key];
    };
    ActionBase2.prototype.getEvent = function() {
      return this.constructor.event;
    };
    ActionBase2.prototype.handleSuccess = function(resolution, nextGroup) {
      if (resolution === void 0) {
        resolution = Resolution.succeeded;
      }
      return Promise.resolve(new ActionResult(resolution, nextGroup));
    };
    ActionBase2.prototype.handleFail = function(event, failReason) {
      return Promise.reject(new ActionExecutionError(event, failReason));
    };
    return ActionBase2;
  }();
  var ElementNotFoundError = function(_super) {
    __extends(ElementNotFoundError2, _super);
    function ElementNotFoundError2(xpath, parent) {
      if (parent === void 0) {
        parent = document;
      }
      var _this = _super.call(this) || this;
      _this.message = `Couldn't find "`.concat(xpath, '" element in "').concat(parent.nodeName, '" parent.');
      return _this;
    }
    return ElementNotFoundError2;
  }(HandledError);
  var MultipleElementsError = function(_super) {
    __extends(MultipleElementsError2, _super);
    function MultipleElementsError2(xpath, parent) {
      if (parent === void 0) {
        parent = document;
      }
      var _this = _super.call(this) || this;
      _this.message = "Multiple elements matches ".concat(xpath, " selector in ").concat(parent.nodeName, " parent.");
      return _this;
    }
    return MultipleElementsError2;
  }(HandledError);
  var XPathUtil = function() {
    function XPathUtil2() {
    }
    XPathUtil2.getSingleElementByXPath = function(xpath, parent) {
      var elements = XPathUtil2.getAllElementsByXpath(xpath, parent);
      if (elements.length > 1)
        throw new MultipleElementsError(xpath, parent);
      return elements.shift();
    };
    XPathUtil2.getAllElementsByXpath = function(xpath, parent) {
      var elements = [];
      var parentDocument = XPathUtil2.getNodeDocument(parent);
      var query = parentDocument.evaluate(xpath, parentDocument, null, XPathResult.ORDERED_NODE_ITERATOR_TYPE, null);
      var element = query.iterateNext();
      while (element) {
        elements.push(element);
        element = query.iterateNext();
      }
      if (elements.length === 0)
        throw new ElementNotFoundError(xpath, parentDocument);
      return elements;
    };
    XPathUtil2.isIFrame = function(node) {
      return node instanceof HTMLIFrameElement;
    };
    XPathUtil2.getNodeDocument = function(node) {
      if (!node)
        return document;
      return this.isIFrame(node) ? node.contentWindow.document : document;
    };
    return XPathUtil2;
  }();
  var NodeActionBase = function(_super) {
    __extends(NodeActionBase2, _super);
    function NodeActionBase2(xpath, parent) {
      var _this = _super.call(this) || this;
      _this.xpath = xpath;
      _this.parent = parent;
      return _this;
    }
    NodeActionBase2.prototype.getNode = function(xpath, parent) {
      var parentNode = parent ? this.getNode(parent) : void 0;
      return XPathUtil.getSingleElementByXPath(xpath, parentNode);
    };
    return NodeActionBase2;
  }(ActionBase);
  var ClickAction = function(_super) {
    __extends(ClickAction2, _super);
    function ClickAction2(xpath, parent) {
      return _super.call(this, xpath, parent) || this;
    }
    ClickAction2.prototype.execute = function() {
      return __awaiter(this, void 0, void 0, function() {
        var element;
        return __generator(this, function(_a) {
          try {
            element = this.getNode(this.xpath, this.parent);
            this.invokeClick(element);
            return [2, this.handleSuccess()];
          } catch (error) {
            return [2, this.handleFail(ClickAction2.event, error)];
          }
          return [2];
        });
      });
    };
    ClickAction2.prototype.invokeClick = function(element) {
      element.click();
    };
    ClickAction2.event = ActionEvents.click;
    return ClickAction2;
  }(NodeActionBase);
  var ActionTimeoutError = function(_super) {
    __extends(ActionTimeoutError2, _super);
    function ActionTimeoutError2(xpath, timeout) {
      var _this = _super.call(this) || this;
      _this.message = `Couldn't find "`.concat(xpath, '" element within ').concat(timeout, "ms.");
      return _this;
    }
    return ActionTimeoutError2;
  }(HandledError);
  var DomObserverBase = function() {
    function DomObserverBase2(timeout, parent, interval) {
      if (interval === void 0) {
        interval = 500;
      }
      this.timeout = timeout;
      this.parent = parent;
      this.interval = interval;
    }
    Object.defineProperty(DomObserverBase2.prototype, "isTimedOut", {
      get: function() {
        return !this.timeoutTime || Date.now() > this.timeoutTime;
      },
      enumerable: false,
      configurable: true
    });
    DomObserverBase2.prototype.onElementVisible = function() {
      return __awaiter(this, void 0, void 0, function() {
        var promise;
        var _this = this;
        return __generator(this, function(_a) {
          promise = new Promise(function(resolve, reject) {
            _this.promiseResolve = resolve;
            _this.promiseReject = reject;
          });
          this.timeoutTime = Date.now() + this.timeout;
          this.createTimeout();
          return [2, promise];
        });
      });
    };
    DomObserverBase2.prototype.dispose = function() {
      var _this = this;
      clearTimeout(this.timeoutInstance);
      Object.keys(this).forEach(function(key) {
        return delete _this[key];
      });
    };
    DomObserverBase2.prototype.createTimeout = function() {
      var _this = this;
      this.timeoutInstance = window.setTimeout(function() {
        return _this.onTimeout();
      }, this.interval);
    };
    DomObserverBase2.prototype.onTimeout = function() {
      var _a, _b, _c;
      try {
        return (_a = this.promiseResolve) === null || _a === void 0 ? void 0 : _a.call(this, this.getTargetElement());
      } catch (error) {
        if (!(error instanceof ElementNotFoundError))
          return (_b = this.promiseReject) === null || _b === void 0 ? void 0 : _b.call(this, error);
        if (this.isTimedOut)
          return (_c = this.promiseReject) === null || _c === void 0 ? void 0 : _c.call(this, this.getActionTimeoutError());
      }
      this.createTimeout();
    };
    DomObserverBase2.prototype.getNode = function(xpath, parent) {
      return xpath ? XPathUtil.getSingleElementByXPath(xpath, parent) : void 0;
    };
    return DomObserverBase2;
  }();
  var SingleDomObserver = function(_super) {
    __extends(SingleDomObserver2, _super);
    function SingleDomObserver2(xpath, timeout, parent, interval) {
      if (interval === void 0) {
        interval = 500;
      }
      var _this = _super.call(this, timeout, parent, interval) || this;
      _this.xpath = xpath;
      _this.parent = parent;
      _this.interval = interval;
      return _this;
    }
    SingleDomObserver2.prototype.getTargetElement = function() {
      var parentNode = this.getNode(this.parent);
      return this.getNode(this.xpath, parentNode);
    };
    SingleDomObserver2.prototype.getActionTimeoutError = function() {
      return new ActionTimeoutError(this.xpath, this.timeout);
    };
    return SingleDomObserver2;
  }(DomObserverBase);
  var ClickWhenVisibleAction = function(_super) {
    __extends(ClickWhenVisibleAction2, _super);
    function ClickWhenVisibleAction2(xpath, timeout, parent) {
      var _this = _super.call(this, xpath, parent) || this;
      _this.timeout = timeout;
      return _this;
    }
    ClickWhenVisibleAction2.prototype.execute = function() {
      return __awaiter(this, void 0, void 0, function() {
        var element, error_1;
        return __generator(this, function(_a) {
          switch (_a.label) {
            case 0:
              _a.trys.push([0, 2, , 3]);
              this.domObserver = new SingleDomObserver(this.xpath, this.timeout, this.parent);
              return [4, this.domObserver.onElementVisible()];
            case 1:
              element = _a.sent();
              this.invokeClick(element);
              return [2, this.handleSuccess()];
            case 2:
              error_1 = _a.sent();
              return [2, this.handleFail(ActionEvents.clickWhenVisible, error_1)];
            case 3:
              return [2];
          }
        });
      });
    };
    ClickWhenVisibleAction2.prototype.dispose = function() {
      var _a;
      (_a = this.domObserver) === null || _a === void 0 ? void 0 : _a.dispose();
      _super.prototype.dispose.call(this);
    };
    ClickWhenVisibleAction2.event = ActionEvents.clickWhenVisible;
    return ClickWhenVisibleAction2;
  }(ClickAction);
  var ParseActionError = function(_super) {
    __extends(ParseActionError2, _super);
    function ParseActionError2(event) {
      var _this = _super.call(this) || this;
      _this.event = event;
      _this.message = 'Unable to parse the "'.concat(event, '" action.');
      return _this;
    }
    return ParseActionError2;
  }(HandledError);
  var Validator = function() {
    function Validator2() {
    }
    Validator2.isObjectWithKeys = function(object) {
      return !!object && !this.isNumber(object) && !this.isString(object) && !this.isArray(object) && this.notEmptyObjectKeys(object);
    };
    Validator2.isNumber = function(number) {
      return typeof number === "number";
    };
    Validator2.nonEmptyString = function(string) {
      return this.isString(string) && string.length > 0;
    };
    Validator2.isString = function(string) {
      return typeof string === "string";
    };
    Validator2.isEmptyArray = function(array) {
      return this.isArray(array) && array.length === 0;
    };
    Validator2.nonEmptyArray = function(array) {
      return this.isArray(array) && !!array.length;
    };
    Validator2.isArray = function(array) {
      return Array.isArray(array);
    };
    Validator2.isQueryString = function(query) {
      if (!this.nonEmptyString(query))
        return false;
      var querySplit = query.split("=");
      if (querySplit.length !== 2)
        return false;
      for (var _i = 0, querySplit_1 = querySplit; _i < querySplit_1.length; _i++) {
        var value = querySplit_1[_i];
        if (!this.nonEmptyString(value))
          return false;
      }
      return true;
    };
    Validator2.isValidUrl = function(url) {
      try {
        new URL(url);
        return true;
      } catch (_a) {
        return false;
      }
    };
    Validator2.isRegex = function(regex) {
      return this.nonEmptyString(regex) && regex[0] === "/";
    };
    Validator2.isEnumValue = function(value, enumType) {
      return !!(enumType === null || enumType === void 0 ? void 0 : enumType[value]);
    };
    Validator2.notEmptyObjectKeys = function(object) {
      return Object.keys(object).length > 0;
    };
    Validator2.isBoolean = function(value) {
      return typeof value === "boolean";
    };
    return Validator2;
  }();
  var GenericActionParserBase = function() {
    function GenericActionParserBase2() {
    }
    GenericActionParserBase2.prototype.validateXpath = function(xpath) {
      return Validator.nonEmptyString(xpath);
    };
    GenericActionParserBase2.prototype.validateTimeout = function(timeout) {
      return Validator.isNumber(timeout);
    };
    GenericActionParserBase2.prototype.validateUrl = function(url) {
      return Validator.isValidUrl(url);
    };
    GenericActionParserBase2.prototype.validateClassName = function(className) {
      return Validator.nonEmptyString(className);
    };
    GenericActionParserBase2.prototype.validatePosition = function(position) {
      return Validator.nonEmptyString(position);
    };
    GenericActionParserBase2.prototype.throwParseError = function(event) {
      throw new ParseActionError(event);
    };
    return GenericActionParserBase2;
  }();
  var ClickWhenVisibleActionParser = function(_super) {
    __extends(ClickWhenVisibleActionParser2, _super);
    function ClickWhenVisibleActionParser2() {
      return _super !== null && _super.apply(this, arguments) || this;
    }
    ClickWhenVisibleActionParser2.prototype.parse = function(action) {
      if (!this.validateXpath(action.xpath) || !this.validateTimeout(action.timeout))
        this.throwParseError(ClickWhenVisibleAction.event);
      return new ClickWhenVisibleAction(action.xpath, action.timeout, action.parent);
    };
    return ClickWhenVisibleActionParser2;
  }(GenericActionParserBase);
  var DelayAction = function(_super) {
    __extends(DelayAction2, _super);
    function DelayAction2(timeout) {
      var _this = _super.call(this) || this;
      _this.timeout = timeout;
      _this.timer = void 0;
      return _this;
    }
    DelayAction2.prototype.execute = function() {
      return __awaiter(this, void 0, void 0, function() {
        var _this = this;
        return __generator(this, function(_a) {
          return [2, new Promise(function(resolve) {
            _this.timer = window.setTimeout(function() {
              return resolve(_this.handleSuccess(Resolution.succeeded));
            }, _this.timeout);
          })];
        });
      });
    };
    DelayAction2.prototype.disposeTimer = function() {
      if (!this.timer)
        return;
      clearTimeout(this.timer);
      this.timer = void 0;
    };
    DelayAction2.prototype.dispose = function() {
      this.disposeTimer();
      _super.prototype.dispose.call(this);
    };
    DelayAction2.event = ActionEvents.delay;
    return DelayAction2;
  }(ActionBase);
  var DelayActionParser = function(_super) {
    __extends(DelayActionParser2, _super);
    function DelayActionParser2() {
      return _super !== null && _super.apply(this, arguments) || this;
    }
    DelayActionParser2.prototype.parse = function(action) {
      if (!this.validateTimeout(action.timeout))
        this.throwParseError(DelayAction.event);
      return new DelayAction(action.timeout);
    };
    return DelayActionParser2;
  }(GenericActionParserBase);
  var ExecuteScriptAction = function(_super) {
    __extends(ExecuteScriptAction2, _super);
    function ExecuteScriptAction2(executionMethod) {
      var _this = _super.call(this) || this;
      _this.executionMethod = executionMethod;
      return _this;
    }
    ExecuteScriptAction2.prototype.execute = function() {
      return __awaiter(this, void 0, void 0, function() {
        return __generator(this, function(_a) {
          try {
            this.executionMethod();
            return [2, this.handleSuccess()];
          } catch (error) {
            return [2, this.handleFail(ActionEvents.executeScript, error)];
          }
          return [2];
        });
      });
    };
    ExecuteScriptAction2.event = ActionEvents.executeScript;
    return ExecuteScriptAction2;
  }(ActionBase);
  var ExecuteScriptActionParser = function(_super) {
    __extends(ExecuteScriptActionParser2, _super);
    function ExecuteScriptActionParser2() {
      return _super !== null && _super.apply(this, arguments) || this;
    }
    ExecuteScriptActionParser2.prototype.parse = function(action) {
      try {
        var parsedMethod = this.parseExecutionMethod(action.script);
        return new ExecuteScriptAction(parsedMethod);
      } catch (error) {
        this.throwParseError(ExecuteScriptAction.event);
      }
    };
    ExecuteScriptActionParser2.prototype.parseExecutionMethod = function(script) {
      if (!this.validateScript(script))
        throw new Error();
      return Function(script);
    };
    ExecuteScriptActionParser2.prototype.validateScript = function(script) {
      return Validator.nonEmptyString(script);
    };
    return ExecuteScriptActionParser2;
  }(GenericActionParserBase);
  var InjectStylesAction = function(_super) {
    __extends(InjectStylesAction2, _super);
    function InjectStylesAction2(stylesheetUrl) {
      var _this = _super.call(this) || this;
      _this.stylesheetUrl = stylesheetUrl;
      return _this;
    }
    InjectStylesAction2.prototype.dispose = function() {
      for (var key in this)
        if (this.hasOwnProperty(key))
          delete this[key];
    };
    InjectStylesAction2.prototype.execute = function() {
      try {
        this.injectStyles();
        return this.handleSuccess();
      } catch (error) {
        return this.handleFail(InjectStylesAction2.event, error);
      }
    };
    InjectStylesAction2.prototype.injectStyles = function() {
      var stylesheet = document.createElement("link");
      stylesheet.href = this.stylesheetUrl;
      stylesheet.type = "text/css";
      stylesheet.rel = "stylesheet";
      document.getElementsByTagName("head")[0].appendChild(stylesheet);
    };
    InjectStylesAction2.event = ActionEvents.injectStyles;
    return InjectStylesAction2;
  }(ActionBase);
  var InjectStylesActionParser = function(_super) {
    __extends(InjectStylesActionParser2, _super);
    function InjectStylesActionParser2() {
      return _super !== null && _super.apply(this, arguments) || this;
    }
    InjectStylesActionParser2.prototype.parse = function(action) {
      if (!this.validateUrl(action.stylesheetUrl))
        this.throwParseError(InjectStylesAction.event);
      return new InjectStylesAction(action.stylesheetUrl);
    };
    return InjectStylesActionParser2;
  }(GenericActionParserBase);
  var ComponentActionParserBase = function(_super) {
    __extends(ComponentActionParserBase2, _super);
    function ComponentActionParserBase2() {
      return _super !== null && _super.apply(this, arguments) || this;
    }
    ComponentActionParserBase2.prototype.parseResolveConditions = function(conditions) {
      var _this = this;
      return conditions.map(function(condition) {
        var resolveCondition = { elements: _this.parseElements(condition.elements) };
        var groupId = _this.parseGroupId(condition);
        if (groupId)
          resolveCondition.groupId = condition.groupId;
        return resolveCondition;
      });
    };
    ComponentActionParserBase2.prototype.parseElements = function(elements) {
      var _this = this;
      return elements.map(function(el) {
        return typeof el === "string" ? _this.parseStringNodeComponent(el) : _this.parseObjectNodeComponent(el);
      });
    };
    ComponentActionParserBase2.prototype.parseStringNodeComponent = function(element) {
      if (!Validator.nonEmptyString(element))
        throw new Error();
      return { xpath: element, multipleMatch: false };
    };
    ComponentActionParserBase2.prototype.parseObjectNodeComponent = function(element) {
      var multipleMatch = element.hasOwnProperty("multipleMatch") ? element.multipleMatch : false;
      if (!this.validateElementWithParent(element) || !this.validateMultipleMatchFlag(multipleMatch))
        throw new Error();
      return __assign(__assign({}, element), { multipleMatch });
    };
    ComponentActionParserBase2.prototype.validateElementWithParent = function(element) {
      return Validator.nonEmptyString(element.xpath) && (!element.hasOwnProperty("parent") || Validator.nonEmptyString(element.parent));
    };
    ComponentActionParserBase2.prototype.validateMultipleMatchFlag = function(multipleMatch) {
      return Validator.isBoolean(multipleMatch);
    };
    ComponentActionParserBase2.prototype.parseGroupId = function(condition) {
      if (!condition.hasOwnProperty("groupId"))
        return void 0;
      if (!Validator.nonEmptyString(condition.groupId))
        throw Error();
      return condition.groupId;
    };
    ComponentActionParserBase2.prototype.validateHtmlContent = function(htmlContent) {
      return Validator.nonEmptyString(htmlContent);
    };
    return ComponentActionParserBase2;
  }(GenericActionParserBase);
  var EventEmitter = function() {
    function EventEmitter2() {
      this.events = {};
    }
    EventEmitter2.prototype.addListener = function(event, listener) {
      var _this = this;
      if (!this.events[event])
        this.events[event] = [];
      this.events[event].push(listener);
      return function() {
        return _this.removeListener(event, listener);
      };
    };
    EventEmitter2.prototype.removeListener = function(event, listener) {
      if (!this.events[event])
        return;
      var idx = this.events[event].indexOf(listener);
      if (idx > -1)
        this.events[event].splice(idx, 1);
    };
    EventEmitter2.prototype.removeAllListeners = function() {
      var _this = this;
      Object.keys(this.events).forEach(function(event) {
        return _this.events[event] = [];
      });
    };
    EventEmitter2.prototype.emit = function(event) {
      var _this = this;
      var args = [];
      for (var _i = 1; _i < arguments.length; _i++) {
        args[_i - 1] = arguments[_i];
      }
      if (!this.events[event])
        return;
      __spreadArray([], this.events[event], true).forEach(function(listener) {
        return listener.apply(_this, args);
      });
    };
    EventEmitter2.prototype.once = function(event, listener) {
      var _this = this;
      var remove = this.addListener(event, function() {
        var args = [];
        for (var _i = 0; _i < arguments.length; _i++) {
          args[_i] = arguments[_i];
        }
        remove();
        listener.apply(_this, args);
      });
      return remove;
    };
    return EventEmitter2;
  }();
  var eventEmitter = new EventEmitter();
  var ScenarioEvent;
  (function(ScenarioEvent2) {
    ScenarioEvent2["onBeforeLastAction"] = "scenario.onBeforeLastAction";
    ScenarioEvent2["onError"] = "scenario.onError";
  })(ScenarioEvent || (ScenarioEvent = {}));
  var TrackEvent;
  (function(TrackEvent2) {
    TrackEvent2["TooltipResolved"] = "track.tooltipResolved";
    TrackEvent2["TooltipClosed"] = "track.tooltipClosed";
    TrackEvent2["NotificationResolved"] = "track.notificationResolved";
    TrackEvent2["NotificationClosed"] = "track.notificationClosed";
  })(TrackEvent || (TrackEvent = {}));
  var GroupId;
  (function(GroupId2) {
    GroupId2["ScenarioClosed"] = "scenario-closed";
    GroupId2["ScenarioRevoked"] = "scenario-revoked";
  })(GroupId || (GroupId = {}));
  var ComponentConditionsError = function(_super) {
    __extends(ComponentConditionsError2, _super);
    function ComponentConditionsError2(element, failReason) {
      var _this = _super.call(this) || this;
      _this.element = element;
      _this.failReason = failReason;
      _this.message = "Resolve Condition Failed: ".concat(_this.failReason.message);
      return _this;
    }
    Object.defineProperty(ComponentConditionsError2.prototype, "errorDetails", {
      get: function() {
        var _a;
        return [{
          key: "".concat(this.element.xpath, " ").concat((_a = this.element.parent) !== null && _a !== void 0 ? _a : ""),
          description: this.failReason.message,
          failReason: this.failReason
        }];
      },
      enumerable: false,
      configurable: true
    });
    return ComponentConditionsError2;
  }(HandledError);
  var ComponentDuplicateElementError = function(_super) {
    __extends(ComponentDuplicateElementError2, _super);
    function ComponentDuplicateElementError2(uniqueId) {
      var _this = _super.call(this) || this;
      _this.uniqueId = uniqueId;
      _this.message = "Element is not unique: ".concat(_this.uniqueId, " id already exists in DOM.");
      return _this;
    }
    return ComponentDuplicateElementError2;
  }(HandledError);
  var UniqueId = function() {
    function UniqueId2() {
    }
    UniqueId2.generate = function() {
      return Math.random().toString(36).substr(2, 9);
    };
    return UniqueId2;
  }();
  var ComponentBase = function() {
    function ComponentBase2(content) {
      this.content = content;
      this.domListeners = [];
      this.uniqueId = UniqueId.generate();
    }
    ComponentBase2.prototype.renderComponent = function(resolveConditions, onResolve, onError) {
      try {
        this.onResolve = onResolve;
        this.render();
        this.registerConditionListeners(resolveConditions);
      } catch (error) {
        onError(error);
      }
    };
    ComponentBase2.prototype.dispose = function() {
      var _a;
      this.removeDomListeners();
      (_a = this.element) === null || _a === void 0 ? void 0 : _a.remove();
      for (var key in this)
        if (this.hasOwnProperty(key))
          delete this[key];
    };
    ComponentBase2.prototype.render = function() {
      if (document.getElementById(this.uniqueId))
        throw new ComponentDuplicateElementError(this.uniqueId);
      this.element = this.buildElement();
      this.appendComponentElement();
    };
    ComponentBase2.prototype.appendComponentElement = function() {
      document.body.appendChild(this.element);
    };
    ComponentBase2.prototype.registerConditionListeners = function(resolveConditions) {
      var _this = this;
      resolveConditions.forEach(function(condition) {
        var elements = _this.getConditionElements(condition.elements);
        elements.forEach(function(element) {
          return _this.addDomListener(element, "click", function() {
            return _this.onResolve(condition);
          });
        });
      });
    };
    ComponentBase2.prototype.getConditionElements = function(components) {
      var _this = this;
      var elements = [];
      components.forEach(function(component) {
        try {
          elements = elements.concat(_this.getElement(component));
        } catch (error) {
          throw new ComponentConditionsError(component, error);
        }
      });
      return elements;
    };
    ComponentBase2.prototype.getElement = function(component) {
      var resolveElementsMethod = component.multipleMatch ? XPathUtil.getAllElementsByXpath : XPathUtil.getSingleElementByXPath;
      return resolveElementsMethod(component.xpath, this.getParentNode(component.parent));
    };
    ComponentBase2.prototype.getParentNode = function(parent) {
      return parent ? XPathUtil.getSingleElementByXPath(parent) : void 0;
    };
    ComponentBase2.prototype.addDomListener = function(target, type, callback) {
      this.domListeners.push({ target, type, callback });
      target.addEventListener(type, callback);
    };
    ComponentBase2.prototype.removeDomListeners = function() {
      this.domListeners.forEach(function(listener) {
        return listener.target.removeEventListener(listener.type, listener.callback);
      });
    };
    return ComponentBase2;
  }();
  var NotificationComponent = function(_super) {
    __extends(NotificationComponent2, _super);
    function NotificationComponent2(content, className) {
      var _this = _super.call(this, content) || this;
      _this.content = content;
      _this.className = className;
      return _this;
    }
    NotificationComponent2.prototype.buildElement = function() {
      var notification = document.createElement("div");
      notification.id = this.uniqueId;
      notification.className = this.className;
      notification.innerHTML = this.content;
      return notification;
    };
    return NotificationComponent2;
  }(ComponentBase);
  var RenderComponentActionBase = function(_super) {
    __extends(RenderComponentActionBase2, _super);
    function RenderComponentActionBase2() {
      var _this = _super !== null && _super.apply(this, arguments) || this;
      _this.resolveConditions = [];
      _this.resolve = function() {
        return void 0;
      };
      _this.reject = function() {
        return void 0;
      };
      return _this;
    }
    RenderComponentActionBase2.prototype.execute = function() {
      var _this = this;
      return new Promise(function(resolve, reject) {
        _this.resolve = resolve;
        _this.reject = reject;
        _this.setComponent();
      });
    };
    RenderComponentActionBase2.prototype.dispose = function() {
      this.disposeComponent();
      _super.prototype.dispose.call(this);
    };
    RenderComponentActionBase2.prototype.getResolveConditionsGroupIds = function() {
      return this.resolveConditions.map(function(condition) {
        return condition.groupId;
      });
    };
    RenderComponentActionBase2.prototype.disposeComponent = function() {
      var _a;
      (_a = this.component) === null || _a === void 0 ? void 0 : _a.dispose();
      this.component = void 0;
    };
    RenderComponentActionBase2.prototype.setComponent = function() {
      var _this = this;
      this.component = this.buildComponent();
      this.component.renderComponent(this.resolveConditions, function(condition) {
        return _this.onResolve(condition);
      }, function(error) {
        return _this.reject(error);
      });
    };
    RenderComponentActionBase2.prototype.onResolve = function(condition) {
      this.disposeComponent();
      this.resolve(new ActionResult(Resolution.succeeded, condition.groupId));
    };
    return RenderComponentActionBase2;
  }(NodeActionBase);
  var NotificationAction = function(_super) {
    __extends(NotificationAction2, _super);
    function NotificationAction2(content, className, resolveConditions, trackableContent) {
      var _this = _super.call(this, "", className) || this;
      _this.content = content;
      _this.className = className;
      _this.resolveConditions = resolveConditions;
      _this.trackableContent = trackableContent;
      return _this;
    }
    NotificationAction2.prototype.onResolve = function(condition) {
      eventEmitter.emit(this.getTrackEventFromCondition(condition), { content: this.trackableContent });
      _super.prototype.onResolve.call(this, condition);
    };
    NotificationAction2.prototype.getTrackEventFromCondition = function(condition) {
      if (condition.groupId === GroupId.ScenarioClosed)
        return TrackEvent.NotificationClosed;
      return TrackEvent.NotificationResolved;
    };
    NotificationAction2.prototype.buildComponent = function() {
      return new NotificationComponent(this.content, this.className);
    };
    NotificationAction2.event = ActionEvents.notification;
    return NotificationAction2;
  }(RenderComponentActionBase);
  var NotificationActionParser = function(_super) {
    __extends(NotificationActionParser2, _super);
    function NotificationActionParser2() {
      return _super !== null && _super.apply(this, arguments) || this;
    }
    NotificationActionParser2.prototype.parse = function(action) {
      if (!this.validateNotificationData(action))
        this.throwParseError(action.event);
      return this.getParsedNotificationAction(action);
    };
    NotificationActionParser2.prototype.validateNotificationData = function(action) {
      return this.validateHtmlContent(action.htmlContent) && this.validateActionClassName(action);
    };
    NotificationActionParser2.prototype.getParsedNotificationAction = function(action) {
      try {
        var htmlContent = action.htmlContent, className = action.className, resolveConditions = action.resolveConditions;
        var parsedConditions = this.parseResolveConditions(resolveConditions);
        return new NotificationAction(htmlContent, className !== null && className !== void 0 ? className : "", parsedConditions);
      } catch (e) {
        this.throwParseError(action.event);
      }
    };
    NotificationActionParser2.prototype.validateActionClassName = function(action) {
      return !action.hasOwnProperty("className") || this.validateClassName(action["className"]);
    };
    return NotificationActionParser2;
  }(ComponentActionParserBase);
  var ScrollAction = function(_super) {
    __extends(ScrollAction2, _super);
    function ScrollAction2(xpath, timeout, scrollToOptions, parent) {
      var _this = _super.call(this, xpath, parent) || this;
      _this.timeout = timeout;
      _this.scrollToOptions = scrollToOptions;
      _this.domObserver = new SingleDomObserver(xpath, timeout, parent);
      return _this;
    }
    ScrollAction2.prototype.execute = function() {
      return __awaiter(this, void 0, void 0, function() {
        var element, scrollOptions, error_1;
        return __generator(this, function(_a) {
          switch (_a.label) {
            case 0:
              _a.trys.push([0, 2, , 3]);
              this.domObserver = new SingleDomObserver(this.xpath, this.timeout, this.parent);
              return [4, this.domObserver.onElementVisible()];
            case 1:
              element = _a.sent();
              scrollOptions = this.scrollToOptions ? this.scrollToOptions : { left: element.scrollWidth, top: element.scrollHeight };
              element.scrollBy(scrollOptions);
              return [2, this.handleSuccess()];
            case 2:
              error_1 = _a.sent();
              return [2, this.handleFail(ActionEvents.scroll, error_1)];
            case 3:
              return [2];
          }
        });
      });
    };
    ScrollAction2.event = ActionEvents.scroll;
    return ScrollAction2;
  }(NodeActionBase);
  var ScrollActionParser = function(_super) {
    __extends(ScrollActionParser2, _super);
    function ScrollActionParser2() {
      return _super !== null && _super.apply(this, arguments) || this;
    }
    ScrollActionParser2.prototype.parse = function(action) {
      if (!this.validateXpath(action.xpath) || !this.validateTimeout(action.timeout) || !this.validateScrollToOptionsGrouped(action))
        this.throwParseError(ScrollAction.event);
      return new ScrollAction(action.xpath, action.timeout, action.scrollToOptions, action.parent);
    };
    ScrollActionParser2.prototype.validateScrollToOptionsGrouped = function(action) {
      return !action.hasOwnProperty("scrollToOptions") || this.validateScrollToOptions(action.scrollToOptions);
    };
    ScrollActionParser2.prototype.validateScrollToOptions = function(value) {
      var scrollToOptions = value;
      return Validator.isObjectWithKeys(value) && Validator.isNumber(scrollToOptions.left) && Validator.isNumber(scrollToOptions.top);
    };
    return ScrollActionParser2;
  }(GenericActionParserBase);
  var TooltipPosition;
  (function(TooltipPosition2) {
    TooltipPosition2["topLeft"] = "topLeft";
    TooltipPosition2["topRight"] = "topRight";
    TooltipPosition2["bottomLeft"] = "bottomLeft";
    TooltipPosition2["bottomRight"] = "bottomRight";
    TooltipPosition2["leftTop"] = "leftTop";
    TooltipPosition2["leftBottom"] = "leftBottom";
    TooltipPosition2["rightTop"] = "rightTop";
    TooltipPosition2["rightBottom"] = "rightBottom";
  })(TooltipPosition || (TooltipPosition = {}));
  var debounce = function(func, delay2) {
    var inDebounce;
    var debouncedFunction = function() {
      var _this = this;
      var args = [];
      for (var _i = 0; _i < arguments.length; _i++) {
        args[_i] = arguments[_i];
      }
      clearTimeout(inDebounce);
      inDebounce = setTimeout(function() {
        return func.apply(_this, args);
      }, delay2);
    };
    debouncedFunction.cancel = function() {
      clearTimeout(inDebounce);
    };
    return debouncedFunction;
  };
  var DEBOUNCE_RESIZE_WAIT_TIME = 100;
  var DEFAULT_BOUNDING_RECT = { x: 0, y: 0 };
  var TooltipComponent = function(_super) {
    __extends(TooltipComponent2, _super);
    function TooltipComponent2(targetNode, targetParent, content, options) {
      var _this = _super.call(this, content) || this;
      _this.targetNode = targetNode;
      _this.targetParent = targetParent;
      _this.content = content;
      _this.options = options;
      _this.debouncedSetPosition = debounce(_this.setPosition.bind(_this), DEBOUNCE_RESIZE_WAIT_TIME);
      return _this;
    }
    TooltipComponent2.prototype.render = function() {
      _super.prototype.render.call(this);
      this.registerPositionListeners();
      this.setPosition();
    };
    TooltipComponent2.prototype.dispose = function() {
      var _a;
      (_a = this.debouncedSetPosition) === null || _a === void 0 ? void 0 : _a.cancel();
      _super.prototype.dispose.call(this);
    };
    TooltipComponent2.prototype.buildElement = function() {
      var tooltip = document.createElement("div");
      tooltip.id = this.uniqueId;
      tooltip.className = "".concat(this.options.className, " position-").concat(this.options.position);
      tooltip.innerHTML = this.content;
      return tooltip;
    };
    TooltipComponent2.prototype.registerPositionListeners = function() {
      var _this = this;
      this.addDomListener(window, "resize", function() {
        return _this.debouncedSetPosition();
      });
      this.addDomListener(this.resolveScrollElement(), "scroll", function() {
        return _this.setPosition();
      });
    };
    Object.defineProperty(TooltipComponent2.prototype, "isParentIFrame", {
      get: function() {
        return XPathUtil.isIFrame(this.targetParent);
      },
      enumerable: false,
      configurable: true
    });
    TooltipComponent2.prototype.resolveScrollElement = function() {
      var _a;
      if (this.isParentIFrame)
        return this.targetNode.ownerDocument;
      return (_a = this.targetParent) !== null && _a !== void 0 ? _a : document;
    };
    TooltipComponent2.prototype.getParentsBoundingRect = function() {
      return this.isParentIFrame ? this.targetParent.getBoundingClientRect() : DEFAULT_BOUNDING_RECT;
    };
    TooltipComponent2.prototype.setPosition = function() {
      if (!this.targetNode)
        return;
      var targetRect = this.targetNode.getBoundingClientRect();
      var parentRect = this.getParentsBoundingRect();
      var spaceBetween = this.options.spaceBetween;
      switch (this.options.position) {
        case TooltipPosition.topLeft:
          this.alignHorizontally(parentRect.x + targetRect.right - this.element.offsetWidth - targetRect.width / 2);
          this.alignVertically(parentRect.y + targetRect.top - this.element.offsetHeight - spaceBetween);
          break;
        case TooltipPosition.topRight:
          this.alignHorizontally(parentRect.x + targetRect.right - targetRect.width / 2);
          this.alignVertically(parentRect.y + targetRect.top - this.element.offsetHeight - spaceBetween);
          break;
        case TooltipPosition.bottomLeft:
          this.alignHorizontally(parentRect.x + targetRect.right - this.element.offsetWidth - targetRect.width / 2);
          this.alignVertically(parentRect.y + targetRect.bottom + spaceBetween);
          break;
        case TooltipPosition.bottomRight:
          this.alignHorizontally(parentRect.x + targetRect.right - targetRect.width / 2);
          this.alignVertically(parentRect.y + targetRect.bottom + spaceBetween);
          break;
        case TooltipPosition.leftTop:
          this.alignHorizontally(parentRect.x + targetRect.left - this.element.offsetWidth - spaceBetween);
          this.alignVertically(parentRect.y + targetRect.bottom - this.element.offsetHeight - targetRect.height / 2);
          break;
        case TooltipPosition.leftBottom:
          this.alignHorizontally(parentRect.x + targetRect.left - this.element.offsetWidth - spaceBetween);
          this.alignVertically(parentRect.y + targetRect.bottom - targetRect.height / 2);
          break;
        case TooltipPosition.rightTop:
          this.alignHorizontally(parentRect.x + targetRect.right + spaceBetween);
          this.alignVertically(parentRect.y + targetRect.bottom - this.element.offsetHeight - targetRect.height / 2);
          break;
        case TooltipPosition.rightBottom:
          this.alignHorizontally(parentRect.x + targetRect.right + spaceBetween);
          this.alignVertically(parentRect.y + targetRect.bottom - targetRect.height / 2);
          break;
      }
    };
    TooltipComponent2.prototype.alignHorizontally = function(left) {
      this.element.style.left = "".concat(left, "px");
    };
    TooltipComponent2.prototype.alignVertically = function(top) {
      this.element.style.top = "".concat(top, "px");
    };
    return TooltipComponent2;
  }(ComponentBase);
  var TooltipAction = function(_super) {
    __extends(TooltipAction2, _super);
    function TooltipAction2(xpath, htmlContent, options, resolveConditions, parent, trackableContent) {
      var _this = _super.call(this, xpath, parent) || this;
      _this.xpath = xpath;
      _this.htmlContent = htmlContent;
      _this.options = options;
      _this.resolveConditions = resolveConditions;
      _this.trackableContent = trackableContent;
      return _this;
    }
    TooltipAction2.prototype.onResolve = function(condition) {
      eventEmitter.emit(this.getTrackEventFromCondition(condition), { content: this.trackableContent });
      _super.prototype.onResolve.call(this, condition);
    };
    TooltipAction2.prototype.getTrackEventFromCondition = function(condition) {
      if (condition.groupId === GroupId.ScenarioClosed)
        return TrackEvent.TooltipClosed;
      return TrackEvent.TooltipResolved;
    };
    TooltipAction2.prototype.buildComponent = function() {
      return new TooltipComponent(this.getNode(this.xpath, this.parent), this.parent ? this.getNode(this.parent) : void 0, this.htmlContent, this.options);
    };
    TooltipAction2.event = ActionEvents.tooltip;
    return TooltipAction2;
  }(RenderComponentActionBase);
  var TooltipActionParser = function(_super) {
    __extends(TooltipActionParser2, _super);
    function TooltipActionParser2() {
      var _this = _super !== null && _super.apply(this, arguments) || this;
      _this.DEFAULT_ARROW_HEIGHT = 12;
      return _this;
    }
    TooltipActionParser2.prototype.parse = function(action) {
      if (!this.validateTooltipActionData(action))
        this.throwParseError(action.event);
      return this.getParsedTooltipAction(action);
    };
    TooltipActionParser2.prototype.validateTooltipActionData = function(action) {
      return this.validateXpath(action.xpath) && this.validateHtmlContent(action.htmlContent) && this.validateParent(action);
    };
    TooltipActionParser2.prototype.getParsedTooltipAction = function(action) {
      try {
        var xpath = action.xpath, parent_1 = action.parent, htmlContent = action.htmlContent;
        var parsedOptions = this.parseOptions(action.options);
        var parsedConditions = this.parseResolveConditions(action.resolveConditions);
        return new TooltipAction(xpath, htmlContent, parsedOptions, parsedConditions, parent_1);
      } catch (e) {
        this.throwParseError(action.event);
      }
    };
    TooltipActionParser2.prototype.validateParent = function(action) {
      return !action.hasOwnProperty("parent") || this.validateXpath(action.parent);
    };
    TooltipActionParser2.prototype.parseOptions = function(options) {
      var _a;
      if (!this.validateTooltipOptions(options))
        this.throwParseError(TooltipAction.event);
      return {
        position: options.position,
        className: (_a = options.className) !== null && _a !== void 0 ? _a : "",
        spaceBetween: options.spaceBetween
      };
    };
    TooltipActionParser2.prototype.validateTooltipOptions = function(options) {
      var position = options.position;
      return Validator.isObjectWithKeys(options) && this.validatePosition(position) && Validator.isEnumValue(position, TooltipPosition) && this.validateTooltipClassName(options) && this.validateSpaceBetween(options);
    };
    TooltipActionParser2.prototype.validateTooltipClassName = function(options) {
      return !options.hasOwnProperty("className") || Validator.isString(options.className);
    };
    TooltipActionParser2.prototype.validateSpaceBetween = function(options) {
      if (!options.hasOwnProperty("spaceBetween"))
        options.spaceBetween = this.DEFAULT_ARROW_HEIGHT;
      return Validator.isNumber(options.spaceBetween);
    };
    return TooltipActionParser2;
  }(ComponentActionParserBase);
  var MultipleDomObserver = function(_super) {
    __extends(MultipleDomObserver2, _super);
    function MultipleDomObserver2(xpaths, timeout, parent, interval) {
      if (interval === void 0) {
        interval = 500;
      }
      var _this = _super.call(this, timeout, parent, interval) || this;
      _this.xpaths = xpaths;
      _this.parent = parent;
      _this.interval = interval;
      return _this;
    }
    MultipleDomObserver2.prototype.getTargetElement = function() {
      var parentNode = this.getNode(this.parent);
      for (var _i = 0, _a = this.xpaths; _i < _a.length; _i++) {
        var xpath = _a[_i];
        var node = this.getNode(xpath, parentNode);
        if (node)
          return node;
      }
      throw new ElementNotFoundError(this.xpaths.join());
    };
    MultipleDomObserver2.prototype.getNode = function(xpath, parent) {
      try {
        return _super.prototype.getNode.call(this, xpath, parent);
      } catch (e) {
        return void 0;
      }
    };
    MultipleDomObserver2.prototype.getActionTimeoutError = function() {
      return new ActionTimeoutError(this.xpaths.join(), this.timeout);
    };
    return MultipleDomObserver2;
  }(DomObserverBase);
  var WaitUntilOneVisibleAction = function(_super) {
    __extends(WaitUntilOneVisibleAction2, _super);
    function WaitUntilOneVisibleAction2(xpaths, timeout, parent) {
      var _this = _super.call(this) || this;
      _this.xpaths = xpaths;
      _this.timeout = timeout;
      _this.parent = parent;
      return _this;
    }
    WaitUntilOneVisibleAction2.prototype.execute = function() {
      return __awaiter(this, void 0, void 0, function() {
        var error_1;
        return __generator(this, function(_a) {
          switch (_a.label) {
            case 0:
              this.setObserver();
              _a.label = 1;
            case 1:
              _a.trys.push([1, 3, , 4]);
              return [4, this.domObserver.onElementVisible()];
            case 2:
              _a.sent();
              return [2, this.handleSuccess()];
            case 3:
              error_1 = _a.sent();
              return [2, Promise.reject(error_1)];
            case 4:
              return [2];
          }
        });
      });
    };
    WaitUntilOneVisibleAction2.prototype.setObserver = function() {
      this.disposeObserver();
      this.domObserver = new MultipleDomObserver(this.xpaths, this.timeout, this.parent);
    };
    WaitUntilOneVisibleAction2.prototype.disposeObserver = function() {
      var _a;
      (_a = this.domObserver) === null || _a === void 0 ? void 0 : _a.dispose();
    };
    WaitUntilOneVisibleAction2.prototype.dispose = function() {
      this.disposeObserver();
      _super.prototype.dispose.call(this);
    };
    WaitUntilOneVisibleAction2.event = ActionEvents.waitUntilOneVisible;
    return WaitUntilOneVisibleAction2;
  }(ActionBase);
  var WaitUntilOneVisibleActionParser = function(_super) {
    __extends(WaitUntilOneVisibleActionParser2, _super);
    function WaitUntilOneVisibleActionParser2() {
      return _super !== null && _super.apply(this, arguments) || this;
    }
    WaitUntilOneVisibleActionParser2.prototype.parse = function(action) {
      if (!Validator.isArray(action.xpaths) || !this.validateXpaths(action.xpaths) || !this.validateTimeout(action.timeout))
        this.throwParseError(WaitUntilOneVisibleAction.event);
      return new WaitUntilOneVisibleAction(action.xpaths, action.timeout, action.parent);
    };
    WaitUntilOneVisibleActionParser2.prototype.validateXpaths = function(xpaths) {
      for (var _i = 0, xpaths_1 = xpaths; _i < xpaths_1.length; _i++) {
        var xpath = xpaths_1[_i];
        if (!this.validateXpath(xpath))
          return false;
      }
      return true;
    };
    return WaitUntilOneVisibleActionParser2;
  }(GenericActionParserBase);
  var WaitUntilVisibleAction = function(_super) {
    __extends(WaitUntilVisibleAction2, _super);
    function WaitUntilVisibleAction2(xpath, timeout, parent) {
      var _this = _super.call(this, xpath, parent) || this;
      _this.timeout = timeout;
      return _this;
    }
    WaitUntilVisibleAction2.prototype.execute = function() {
      return __awaiter(this, void 0, void 0, function() {
        var error_1;
        return __generator(this, function(_a) {
          switch (_a.label) {
            case 0:
              this.setObserver();
              _a.label = 1;
            case 1:
              _a.trys.push([1, 3, , 4]);
              return [4, this.domObserver.onElementVisible()];
            case 2:
              _a.sent();
              return [2, this.handleSuccess()];
            case 3:
              error_1 = _a.sent();
              return [2, Promise.reject(error_1)];
            case 4:
              return [2];
          }
        });
      });
    };
    WaitUntilVisibleAction2.prototype.setObserver = function() {
      this.disposeObserver();
      this.domObserver = new SingleDomObserver(this.xpath, this.timeout, this.parent);
    };
    WaitUntilVisibleAction2.prototype.disposeObserver = function() {
      var _a;
      (_a = this.domObserver) === null || _a === void 0 ? void 0 : _a.dispose();
    };
    WaitUntilVisibleAction2.prototype.dispose = function() {
      this.disposeObserver();
      _super.prototype.dispose.call(this);
    };
    WaitUntilVisibleAction2.event = ActionEvents.waitUntilVisible;
    return WaitUntilVisibleAction2;
  }(NodeActionBase);
  var WaitUntilVisibleActionParser = function(_super) {
    __extends(WaitUntilVisibleActionParser2, _super);
    function WaitUntilVisibleActionParser2() {
      return _super !== null && _super.apply(this, arguments) || this;
    }
    WaitUntilVisibleActionParser2.prototype.parse = function(action) {
      if (!this.validateXpath(action.xpath) || !this.validateTimeout(action.timeout))
        this.throwParseError(WaitUntilVisibleAction.event);
      return new WaitUntilVisibleAction(action.xpath, action.timeout, action.parent);
    };
    return WaitUntilVisibleActionParser2;
  }(GenericActionParserBase);
  var BulkClickAction = function(_super) {
    __extends(BulkClickAction2, _super);
    function BulkClickAction2(xpath, parent) {
      var _this = _super.call(this, xpath, parent) || this;
      _this.CLICK_DELAY = 50;
      return _this;
    }
    BulkClickAction2.prototype.execute = function() {
      var e_1, _a;
      return __awaiter(this, void 0, void 0, function() {
        var elements, elements_1, elements_1_1, element, e_1_1, error_1;
        return __generator(this, function(_b) {
          switch (_b.label) {
            case 0:
              _b.trys.push([0, 14, , 15]);
              elements = this.getNodes(this.xpath, this.parent);
              _b.label = 1;
            case 1:
              _b.trys.push([1, 7, 8, 13]);
              elements_1 = __asyncValues(elements);
              _b.label = 2;
            case 2:
              return [4, elements_1.next()];
            case 3:
              if (!(elements_1_1 = _b.sent(), !elements_1_1.done))
                return [3, 6];
              element = elements_1_1.value;
              return [4, this.delayedBatchClick(element)];
            case 4:
              _b.sent();
              _b.label = 5;
            case 5:
              return [3, 2];
            case 6:
              return [3, 13];
            case 7:
              e_1_1 = _b.sent();
              e_1 = { error: e_1_1 };
              return [3, 13];
            case 8:
              _b.trys.push([8, , 11, 12]);
              if (!(elements_1_1 && !elements_1_1.done && (_a = elements_1.return)))
                return [3, 10];
              return [4, _a.call(elements_1)];
            case 9:
              _b.sent();
              _b.label = 10;
            case 10:
              return [3, 12];
            case 11:
              if (e_1)
                throw e_1.error;
              return [7];
            case 12:
              return [7];
            case 13:
              return [2, this.handleSuccess()];
            case 14:
              error_1 = _b.sent();
              return [2, this.handleFail(BulkClickAction2.event, error_1)];
            case 15:
              return [2];
          }
        });
      });
    };
    BulkClickAction2.prototype.dispose = function() {
      clearTimeout(this.delayTimeout);
      this.delayTimeout = void 0;
      _super.prototype.dispose.call(this);
    };
    BulkClickAction2.prototype.delayedBatchClick = function(element) {
      return __awaiter(this, void 0, void 0, function() {
        var _this = this;
        return __generator(this, function(_a) {
          return [2, new Promise(function(resolve) {
            _this.invokeClick(element);
            _this.delayTimeout = window.setTimeout(resolve, _this.CLICK_DELAY);
          })];
        });
      });
    };
    BulkClickAction2.prototype.getNodes = function(xpath, parent) {
      var parentNode = parent ? this.getNode(parent) : void 0;
      return XPathUtil.getAllElementsByXpath(xpath, parentNode);
    };
    BulkClickAction2.event = ActionEvents.bulkClick;
    return BulkClickAction2;
  }(ClickAction);
  var BulkClickActionParser = function(_super) {
    __extends(BulkClickActionParser2, _super);
    function BulkClickActionParser2() {
      return _super !== null && _super.apply(this, arguments) || this;
    }
    BulkClickActionParser2.prototype.parse = function(action) {
      if (!this.validateXpath(action.xpath))
        this.throwParseError(BulkClickAction.event);
      return new BulkClickAction(action.xpath, action.parent);
    };
    return BulkClickActionParser2;
  }(GenericActionParserBase);
  var ClickActionParser = function(_super) {
    __extends(ClickActionParser2, _super);
    function ClickActionParser2() {
      return _super !== null && _super.apply(this, arguments) || this;
    }
    ClickActionParser2.prototype.parse = function(action) {
      if (!this.validateXpath(action.xpath))
        this.throwParseError(ClickAction.event);
      return new ClickAction(action.xpath, action.parent);
    };
    return ClickActionParser2;
  }(GenericActionParserBase);
  var ClickOneOfAction = function(_super) {
    __extends(ClickOneOfAction2, _super);
    function ClickOneOfAction2(xpaths, timeout, parent) {
      if (timeout === void 0) {
        timeout = 0;
      }
      var _this = _super.call(this) || this;
      _this.xpaths = xpaths;
      _this.timeout = timeout;
      _this.parent = parent;
      return _this;
    }
    ClickOneOfAction2.prototype.execute = function() {
      return __awaiter(this, void 0, void 0, function() {
        var action, error_1;
        return __generator(this, function(_a) {
          switch (_a.label) {
            case 0:
              if (!this.timeout)
                return [2, this.click()];
              _a.label = 1;
            case 1:
              _a.trys.push([1, 3, , 4]);
              action = new WaitUntilOneVisibleAction(this.xpaths, this.timeout, this.parent);
              return [4, action.execute()];
            case 2:
              _a.sent();
              return [2, this.click()];
            case 3:
              error_1 = _a.sent();
              return [2, this.handleFail(ClickOneOfAction2.event, error_1)];
            case 4:
              return [2];
          }
        });
      });
    };
    ClickOneOfAction2.prototype.click = function() {
      return __awaiter(this, void 0, void 0, function() {
        var parentNode, firstElement;
        return __generator(this, function(_a) {
          try {
            parentNode = this.parent ? this.getNode(this.parent) : void 0;
            firstElement = this.findFirstNode(parentNode);
            if (!firstElement)
              return [2, this.handleFail(ClickOneOfAction2.event, new ElementNotFoundError(this.xpaths.join(), parentNode))];
            firstElement.click();
            return [2, this.handleSuccess()];
          } catch (error) {
            return [2, this.handleFail(ClickOneOfAction2.event, error)];
          }
          return [2];
        });
      });
    };
    ClickOneOfAction2.prototype.findFirstNode = function(parentNode) {
      for (var _i = 0, _a = this.xpaths; _i < _a.length; _i++) {
        var xpath = _a[_i];
        var node = this.getNode(xpath, parentNode);
        if (node)
          return node;
      }
      return null;
    };
    ClickOneOfAction2.prototype.getNode = function(xpath, parentNode) {
      try {
        return XPathUtil.getSingleElementByXPath(xpath, parentNode);
      } catch (e) {
        return void 0;
      }
    };
    ClickOneOfAction2.event = ActionEvents.clickOneOf;
    return ClickOneOfAction2;
  }(ActionBase);
  var ClickOneOfActionParser = function(_super) {
    __extends(ClickOneOfActionParser2, _super);
    function ClickOneOfActionParser2() {
      return _super !== null && _super.apply(this, arguments) || this;
    }
    ClickOneOfActionParser2.prototype.parse = function(action) {
      if (!Validator.nonEmptyArray(action.xpaths))
        this.throwParseError(ClickOneOfAction.event);
      for (var _i = 0, _a = action.xpaths; _i < _a.length; _i++) {
        var xpath = _a[_i];
        if (!this.validateXpath(xpath))
          this.throwParseError(ClickOneOfAction.event);
      }
      return new ClickOneOfAction(action.xpaths, action.timeout, action.parent);
    };
    return ClickOneOfActionParser2;
  }(GenericActionParserBase);
  var StopScenarioAction = function(_super) {
    __extends(StopScenarioAction2, _super);
    function StopScenarioAction2() {
      return _super.call(this) || this;
    }
    StopScenarioAction2.prototype.execute = function() {
      return __awaiter(this, void 0, void 0, function() {
        return __generator(this, function(_a) {
          return [2, this.handleSuccess(Resolution.stopped)];
        });
      });
    };
    StopScenarioAction2.event = ActionEvents.stopScenario;
    return StopScenarioAction2;
  }(ActionBase);
  var VerifyOkAction = function(_super) {
    __extends(VerifyOkAction2, _super);
    function VerifyOkAction2(xpath, parent) {
      return _super.call(this, xpath, parent) || this;
    }
    VerifyOkAction2.prototype.execute = function() {
      return __awaiter(this, void 0, void 0, function() {
        return __generator(this, function(_a) {
          try {
            this.getNode(this.xpath, this.parent);
            return [2, this.handleSuccess()];
          } catch (error) {
            return [2, this.handleFail(ActionEvents.verifyOk, error)];
          }
          return [2];
        });
      });
    };
    VerifyOkAction2.event = ActionEvents.verifyOk;
    return VerifyOkAction2;
  }(NodeActionBase);
  var VerifyOkActionParser = function(_super) {
    __extends(VerifyOkActionParser2, _super);
    function VerifyOkActionParser2() {
      return _super !== null && _super.apply(this, arguments) || this;
    }
    VerifyOkActionParser2.prototype.parse = function(action) {
      if (!this.validateXpath(action.xpath))
        this.throwParseError(VerifyOkAction.event);
      return new VerifyOkAction(action.xpath, action.parent);
    };
    return VerifyOkActionParser2;
  }(GenericActionParserBase);
  var PrivacyActionParser = function() {
    function PrivacyActionParser3() {
      this.invalidActions = [];
    }
    PrivacyActionParser3.prototype.parse = function(actions) {
      var _this = this;
      this.invalidActions = [];
      if (!Validator.nonEmptyArray(actions))
        throw new ParseActionsFormatError();
      var parsedActions = [];
      actions.forEach(function(action) {
        try {
          var parsedAction = _this.parseAction(action);
          parsedActions.push(parsedAction);
        } catch (error) {
          _this.handleActionError(error);
        }
      });
      if (this.invalidActions.length)
        throw new ParserInvalidActionsError(this.invalidActions);
      return parsedActions;
    };
    PrivacyActionParser3.prototype.parseAction = function(action) {
      if (!action.event)
        this.throwActionError("unspecified");
      switch (action.event) {
        case ClickAction.event:
          return new ClickActionParser().parse(action);
        case ClickOneOfAction.event:
          return new ClickOneOfActionParser().parse(action);
        case BulkClickAction.event:
          return new BulkClickActionParser().parse(action);
        case ClickWhenVisibleAction.event:
          return new ClickWhenVisibleActionParser().parse(action);
        case DelayAction.event:
          return new DelayActionParser().parse(action);
        case ExecuteScriptAction.event:
          return new ExecuteScriptActionParser().parse(action);
        case InjectStylesAction.event:
          return new InjectStylesActionParser().parse(action);
        case NotificationAction.event:
          return new NotificationActionParser().parse(action);
        case ScrollAction.event:
          return new ScrollActionParser().parse(action);
        case StopScenarioAction.event:
          return new StopScenarioAction();
        case TooltipAction.event:
          return new TooltipActionParser().parse(action);
        case VerifyOkAction.event:
          return new VerifyOkActionParser().parse(action);
        case WaitUntilVisibleAction.event:
          return new WaitUntilVisibleActionParser().parse(action);
        case WaitUntilOneVisibleAction.event:
          return new WaitUntilOneVisibleActionParser().parse(action);
        default:
          this.throwActionError(action.event);
      }
    };
    PrivacyActionParser3.prototype.handleActionError = function(error) {
      if (error instanceof ParseActionError)
        this.invalidActions.push(error.event);
    };
    PrivacyActionParser3.prototype.throwActionError = function(event) {
      throw new ParseActionError(event);
    };
    return PrivacyActionParser3;
  }();
  var PrivacyHooksParser = function() {
    function PrivacyHooksParser2() {
      var _this = this;
      this.invalidHooks = [];
      this.parseHooks = function(parsedHooks, currentKey) {
        var _a;
        var hookType = currentKey;
        var hook = (_a = _this.hooks) === null || _a === void 0 ? void 0 : _a[hookType];
        if (hook && !hook.actions)
          _this.invalidHooks.push(hookType);
        if (hook && !_this.invalidHooks.length)
          parsedHooks[hookType] = { actions: _this.parseHookActions(hook) };
        return parsedHooks;
      };
    }
    PrivacyHooksParser2.prototype.parse = function(hooks) {
      this.hooks = hooks;
      var parsedHooks = Object.keys(HookType).reduce(this.parseHooks, {});
      if (this.invalidHooks.length)
        throw new ParserInvalidHooksError(this.invalidHooks);
      return parsedHooks;
    };
    PrivacyHooksParser2.prototype.parseHookActions = function(hook) {
      return new PrivacyActionParser().parse(hook === null || hook === void 0 ? void 0 : hook.actions);
    };
    return PrivacyHooksParser2;
  }();
  var ExecutionStackBase = function() {
    function ExecutionStackBase2() {
      this.stack = [];
    }
    ExecutionStackBase2.prototype.getStack = function() {
      return this.stack;
    };
    ExecutionStackBase2.prototype.addActionStack = function(actionStack) {
      this.stack.push(actionStack);
    };
    ExecutionStackBase2.prototype.addPageStack = function(pageStack) {
      this.stack.push(pageStack);
    };
    ExecutionStackBase2.prototype.clearStack = function() {
      this.stack = [];
    };
    return ExecutionStackBase2;
  }();
  var ExecutionStack = new ExecutionStackBase();
  var PageActionGroupError = function(_super) {
    __extends(PageActionGroupError2, _super);
    function PageActionGroupError2(groupId) {
      var _this = _super.call(this) || this;
      _this.groupId = groupId;
      _this.message = 'Page group actions could not be executed due to missing "'.concat(_this.groupId, '" group.');
      return _this;
    }
    return PageActionGroupError2;
  }(HandledError);
  var PagePreconditionError = function(_super) {
    __extends(PagePreconditionError2, _super);
    function PagePreconditionError2(target) {
      var _this = _super.call(this) || this;
      _this.target = target;
      _this.message = "Page actions could not be executed due to preconditions are not met.";
      return _this;
    }
    Object.defineProperty(PagePreconditionError2.prototype, "errorDetails", {
      get: function() {
        return [{
          key: "Preconditions",
          description: this.getDetailsDescription()
        }];
      },
      enumerable: false,
      configurable: true
    });
    PagePreconditionError2.prototype.getDetailsDescription = function() {
      return this.target.query ? `Current url and queries doesn't match target "`.concat(this.target.url, '" and [').concat(this.target.query.join(", "), "] queries.") : `Current url doesn't match target "`.concat(this.target.url, '"');
    };
    return PagePreconditionError2;
  }(HandledError);
  var PageResult = function() {
    function PageResult2(resolution) {
      this.resolution = resolution;
    }
    return PageResult2;
  }();
  var PageBase = function() {
    function PageBase2(target, actions, optional) {
      if (optional === void 0) {
        optional = false;
      }
      this.target = target;
      this.actions = actions;
      this.optional = optional;
    }
    PageBase2.prototype.execute = function() {
      return __awaiter(this, void 0, void 0, function() {
        return __generator(this, function(_a) {
          if (!this.verifyPreconditions())
            return [2, this.optional ? this.handleSuccess() : this.handleError(new PagePreconditionError(this.target))];
          ExecutionStack.addPageStack({ target: this.target });
          return [2, this.executeActions()];
        });
      });
    };
    PageBase2.prototype.verifyPreconditions = function() {
      return this.pathnameMatches() && this.queryMatches();
    };
    PageBase2.prototype.dispose = function() {
      this.disposeActions();
      for (var key in this)
        if (this.hasOwnProperty(key))
          delete this[key];
    };
    PageBase2.prototype.pathnameMatches = function() {
      var currentUrl = window.location.origin + window.location.pathname;
      var url = this.target.url;
      if (Validator.isRegex(url)) {
        var re = new RegExp(url.slice(1));
        return re.test(currentUrl);
      } else {
        return url === "*" || url === currentUrl;
      }
    };
    PageBase2.prototype.queryMatches = function() {
      if (this.target.query === void 0 || Validator.isEmptyArray(this.target.query))
        return true;
      for (var _i = 0, _a = this.target.query; _i < _a.length; _i++) {
        var targetQuery = _a[_i];
        if (window.location.search.indexOf(targetQuery) >= 0)
          return true;
      }
      return false;
    };
    PageBase2.prototype.handleSuccess = function(resolution) {
      if (resolution === void 0) {
        resolution = Resolution.succeeded;
      }
      return Promise.resolve(new PageResult(resolution));
    };
    PageBase2.prototype.handleError = function(error) {
      return Promise.reject(error);
    };
    return PageBase2;
  }();
  var ResultUtil = function() {
    function ResultUtil2() {
    }
    ResultUtil2.getActionStack = function(actionResult, action) {
      var stack = {
        event: action.getEvent(),
        nextGroup: actionResult.nextGroup,
        resolution: actionResult.resolution
      };
      return action instanceof NodeActionBase ? __assign(__assign({}, stack), { xpath: action.xpath }) : stack;
    };
    ResultUtil2.getGroupedActionStack = function(actionResult, action, groupId) {
      var stack = this.getActionStack(actionResult, action);
      return __assign(__assign({}, stack), { groupId });
    };
    return ResultUtil2;
  }();
  var GroupedPage = function(_super) {
    __extends(GroupedPage2, _super);
    function GroupedPage2() {
      return _super !== null && _super.apply(this, arguments) || this;
    }
    GroupedPage2.prototype.executeActions = function() {
      return __awaiter(this, void 0, void 0, function() {
        var groupedActionsResult, error_1;
        return __generator(this, function(_a) {
          switch (_a.label) {
            case 0:
              _a.trys.push([0, 2, , 3]);
              return [4, this.executeGroupActions("initial")];
            case 1:
              groupedActionsResult = _a.sent();
              return [3, 3];
            case 2:
              error_1 = _a.sent();
              return [2, this.handleError(error_1)];
            case 3:
              return [2, this.handleSuccess(groupedActionsResult.resolution)];
          }
        });
      });
    };
    GroupedPage2.prototype.disposeActions = function() {
      var _this = this;
      this.actions.forEach(function(group) {
        return _this.disposeGroupAction(group);
      });
    };
    GroupedPage2.prototype.executeGroupActions = function(groupId) {
      var e_1, _a;
      return __awaiter(this, void 0, void 0, function() {
        var group, actionResult, _b, _c, _d, index, action, e_1_1;
        return __generator(this, function(_e) {
          switch (_e.label) {
            case 0:
              group = this.getGroupById(groupId);
              if (!group)
                throw new PageActionGroupError(groupId);
              _e.label = 1;
            case 1:
              _e.trys.push([1, 7, 8, 13]);
              _b = __asyncValues(group.actions.entries());
              _e.label = 2;
            case 2:
              return [4, _b.next()];
            case 3:
              if (!(_c = _e.sent(), !_c.done))
                return [3, 6];
              _d = _c.value, index = _d[0], action = _d[1];
              if (this.isLastAction(action, index, group))
                eventEmitter.emit(ScenarioEvent.onBeforeLastAction, action.getEvent());
              return [4, this.executeAction(action, groupId)];
            case 4:
              actionResult = _e.sent();
              if (actionResult.nextGroup)
                return [2, this.executeGroupActions(actionResult.nextGroup)];
              if (actionResult.resolution !== Resolution.succeeded)
                return [3, 6];
              _e.label = 5;
            case 5:
              return [3, 2];
            case 6:
              return [3, 13];
            case 7:
              e_1_1 = _e.sent();
              e_1 = { error: e_1_1 };
              return [3, 13];
            case 8:
              _e.trys.push([8, , 11, 12]);
              if (!(_c && !_c.done && (_a = _b.return)))
                return [3, 10];
              return [4, _a.call(_b)];
            case 9:
              _e.sent();
              _e.label = 10;
            case 10:
              return [3, 12];
            case 11:
              if (e_1)
                throw e_1.error;
              return [7];
            case 12:
              return [7];
            case 13:
              return [2, actionResult];
          }
        });
      });
    };
    GroupedPage2.prototype.getGroupById = function(groupId) {
      return this.actions.filter(function(group) {
        return group.id === groupId;
      })[0];
    };
    GroupedPage2.prototype.isLastAction = function(groupedAction, index, group) {
      var groupIds = groupedAction.action instanceof RenderComponentActionBase ? groupedAction.action.getResolveConditionsGroupIds() : null;
      var hasNextGroupId = groupIds === null || groupIds === void 0 ? void 0 : groupIds.find(function(groupId) {
        return groupId && groupId != GroupId.ScenarioClosed && groupId != GroupId.ScenarioRevoked;
      });
      return groupedAction.resolveGroup === void 0 && index === group.actions.length - 1 && groupedAction.getEvent() != ActionEvents.stopScenario && !hasNextGroupId;
    };
    GroupedPage2.prototype.disposeGroupAction = function(actionGroup) {
      actionGroup.actions.forEach(function(action) {
        return action.dispose();
      });
    };
    GroupedPage2.prototype.executeAction = function(action, groupId) {
      return __awaiter(this, void 0, void 0, function() {
        var actionResult;
        return __generator(this, function(_a) {
          switch (_a.label) {
            case 0:
              return [4, action.execute()];
            case 1:
              actionResult = _a.sent();
              ExecutionStack.addActionStack(ResultUtil.getGroupedActionStack(actionResult, action, groupId));
              return [2, actionResult];
          }
        });
      });
    };
    return GroupedPage2;
  }(PageBase);
  var Page = function(_super) {
    __extends(Page2, _super);
    function Page2() {
      return _super !== null && _super.apply(this, arguments) || this;
    }
    Page2.prototype.executeActions = function() {
      var e_1, _a;
      var _b;
      return __awaiter(this, void 0, void 0, function() {
        var actionResult, _c, _d, _e, index, action, error_1, e_1_1;
        return __generator(this, function(_f) {
          switch (_f.label) {
            case 0:
              if (this.actions.length === 0)
                return [2, this.handleSuccess(Resolution.succeeded)];
              _f.label = 1;
            case 1:
              _f.trys.push([1, 10, 11, 16]);
              _c = __asyncValues(this.actions.entries());
              _f.label = 2;
            case 2:
              return [4, _c.next()];
            case 3:
              if (!(_d = _f.sent(), !_d.done))
                return [3, 9];
              _e = _d.value, index = _e[0], action = _e[1];
              if (this.isLastAction(index))
                eventEmitter.emit(ScenarioEvent.onBeforeLastAction, action.getEvent());
              _f.label = 4;
            case 4:
              _f.trys.push([4, 6, , 7]);
              return [4, this.executeAction(action)];
            case 5:
              actionResult = _f.sent();
              return [3, 7];
            case 6:
              error_1 = _f.sent();
              return [2, this.handleError(error_1)];
            case 7:
              if (actionResult.resolution !== Resolution.succeeded)
                return [3, 9];
              _f.label = 8;
            case 8:
              return [3, 2];
            case 9:
              return [3, 16];
            case 10:
              e_1_1 = _f.sent();
              e_1 = { error: e_1_1 };
              return [3, 16];
            case 11:
              _f.trys.push([11, , 14, 15]);
              if (!(_d && !_d.done && (_a = _c.return)))
                return [3, 13];
              return [4, _a.call(_c)];
            case 12:
              _f.sent();
              _f.label = 13;
            case 13:
              return [3, 15];
            case 14:
              if (e_1)
                throw e_1.error;
              return [7];
            case 15:
              return [7];
            case 16:
              return [2, this.handleSuccess((_b = actionResult.resolution) !== null && _b !== void 0 ? _b : Resolution.succeeded)];
          }
        });
      });
    };
    Page2.prototype.disposeActions = function() {
      this.actions.forEach(function(action) {
        return action.dispose();
      });
    };
    Page2.prototype.executeAction = function(action) {
      return __awaiter(this, void 0, void 0, function() {
        var actionResult;
        return __generator(this, function(_a) {
          switch (_a.label) {
            case 0:
              return [4, action.execute()];
            case 1:
              actionResult = _a.sent();
              ExecutionStack.addActionStack(ResultUtil.getActionStack(actionResult, action));
              return [2, actionResult];
          }
        });
      });
    };
    Page2.prototype.isLastAction = function(index) {
      return index === this.actions.length - 1;
    };
    return Page2;
  }(PageBase);
  var ParsePageActionsMismatchError = function(_super) {
    __extends(ParsePageActionsMismatchError2, _super);
    function ParsePageActionsMismatchError2() {
      var _this = _super.call(this) || this;
      _this.message = 'Unable to parse the page - either define "actions" or "groupedActions" both of them are not supported in single page.';
      return _this;
    }
    return ParsePageActionsMismatchError2;
  }(HandledError);
  var GroupedAction = function() {
    function GroupedAction2(action, resolveGroup, rejectGroup) {
      this.action = action;
      this.resolveGroup = resolveGroup;
      this.rejectGroup = rejectGroup;
    }
    GroupedAction2.prototype.getEvent = function() {
      return this.action.getEvent();
    };
    GroupedAction2.prototype.execute = function() {
      return __awaiter(this, void 0, void 0, function() {
        var result, actionResult, error_1;
        return __generator(this, function(_a) {
          switch (_a.label) {
            case 0:
              _a.trys.push([0, 2, , 3]);
              return [4, this.action.execute()];
            case 1:
              result = _a.sent();
              actionResult = result.nextGroup ? result : new ActionResult(result.resolution, this.resolveGroup);
              return [2, this.handleSuccess(actionResult)];
            case 2:
              error_1 = _a.sent();
              if (this.rejectGroup)
                return [2, this.handleSuccess(new ActionResult(Resolution.succeeded, this.rejectGroup))];
              return [2, this.handleError(error_1)];
            case 3:
              return [2];
          }
        });
      });
    };
    GroupedAction2.prototype.dispose = function() {
      var _a;
      (_a = this.action) === null || _a === void 0 ? void 0 : _a.dispose();
      for (var key in this)
        if (this.hasOwnProperty(key))
          delete this[key];
    };
    GroupedAction2.prototype.handleSuccess = function(result) {
      return Promise.resolve(result);
    };
    GroupedAction2.prototype.handleError = function(error) {
      return Promise.reject(new ActionExecutionError(this.getEvent(), error));
    };
    return GroupedAction2;
  }();
  var PrivacyGroupedActionParser = function(_super) {
    __extends(PrivacyGroupedActionParser2, _super);
    function PrivacyGroupedActionParser2(actionParser) {
      if (actionParser === void 0) {
        actionParser = new PrivacyActionParser();
      }
      var _this = _super.call(this) || this;
      _this.actionParser = actionParser;
      return _this;
    }
    PrivacyGroupedActionParser2.prototype.parse = function(actionGroups) {
      if (!Validator.nonEmptyArray(actionGroups))
        throw new ParseActionsFormatError();
      return this.parseGroupedActions(actionGroups);
    };
    PrivacyGroupedActionParser2.prototype.parseGroupedActions = function(actionGroups) {
      var _this = this;
      return actionGroups.map(function(group) {
        var parsedActions = _this.actionParser.parse(group.actions);
        var decoratedActions = _this.decorateGroupActions(parsedActions, group.actions);
        return { id: group.id, actions: decoratedActions };
      });
    };
    PrivacyGroupedActionParser2.prototype.decorateGroupActions = function(actions, groupedActions) {
      return actions.map(function(action, index) {
        var _a = groupedActions[index], resolveGroup = _a.resolveGroup, rejectGroup = _a.rejectGroup;
        return new GroupedAction(action, resolveGroup, rejectGroup);
      });
    };
    return PrivacyGroupedActionParser2;
  }(GenericActionParserBase);
  var PrivacyPageParser = function() {
    function PrivacyPageParser2(actionParser) {
      if (actionParser === void 0) {
        actionParser = new PrivacyActionParser();
      }
      this.actionParser = actionParser;
    }
    PrivacyPageParser2.prototype.parse = function(page) {
      var target = this.getParsedPageTarget(page.target);
      if (!this.validateIsOptional(page))
        throw new ParserInvalidPageTargetError();
      var hasSimpleActions = page.hasOwnProperty("actions");
      var hasGroupedActions = page.hasOwnProperty("groupedActions");
      if (hasSimpleActions && hasGroupedActions)
        throw new ParsePageActionsMismatchError();
      return hasSimpleActions ? new Page(target, this.parseActions(page.actions), page.optional) : new GroupedPage(target, this.parseGroupedActions(page.groupedActions), page.optional);
    };
    PrivacyPageParser2.prototype.getParsedPageTarget = function(target) {
      if (this.isValidUrlOrRegex(target))
        return { url: target };
      if (this.isValidPageTarget(target))
        return target;
      throw new ParserInvalidPageTargetError();
    };
    PrivacyPageParser2.prototype.isValidPageTarget = function(target) {
      return Validator.isObjectWithKeys(target) && this.isValidUrlOrRegex(target.url) && this.validatePageTargetQueries(target);
    };
    PrivacyPageParser2.prototype.isValidUrlOrRegex = function(value) {
      return value === "*" || Validator.isValidUrl(value) || Validator.isRegex(value);
    };
    PrivacyPageParser2.prototype.validatePageTargetQueries = function(target) {
      if (target.query === void 0)
        return true;
      if (!Validator.isArray(target.query))
        return false;
      for (var _i = 0, _a = target.query; _i < _a.length; _i++) {
        var query = _a[_i];
        if (!Validator.isQueryString(query))
          return false;
      }
      return true;
    };
    PrivacyPageParser2.prototype.validateIsOptional = function(page) {
      return !page.hasOwnProperty("optional") || Validator.isBoolean(page.optional);
    };
    PrivacyPageParser2.prototype.parseActions = function(actions) {
      return this.actionParser.parse(actions);
    };
    PrivacyPageParser2.prototype.parseGroupedActions = function(actions) {
      return new PrivacyGroupedActionParser(this.actionParser).parse(actions);
    };
    return PrivacyPageParser2;
  }();
  var ScenarioPageHookUnknownError = function(_super) {
    __extends(ScenarioPageHookUnknownError2, _super);
    function ScenarioPageHookUnknownError2(resolution) {
      var _this = _super.call(this) || this;
      _this.resolution = resolution;
      _this.message = "Hook type is unknown.";
      return _this;
    }
    Object.defineProperty(ScenarioPageHookUnknownError2.prototype, "errorDetails", {
      get: function() {
        return [{
          key: "Hook",
          description: "Hook type for '".concat(this.resolution, "' resolution is unknown.")
        }];
      },
      enumerable: false,
      configurable: true
    });
    return ScenarioPageHookUnknownError2;
  }(HandledError);
  var Scenario = function() {
    function Scenario2(name, scenarioPages, hooks) {
      this.name = name;
      this.scenarioPages = scenarioPages;
      this.hooks = hooks;
    }
    Scenario2.prototype.run = function() {
      return __awaiter(this, void 0, void 0, function() {
        return __generator(this, function(_a) {
          return [2, this.executePages()];
        });
      });
    };
    Scenario2.prototype.getHookType = function(result) {
      switch (result.resolution) {
        case Resolution.succeeded:
          return HookType.onSuccess;
        case Resolution.stopped:
        case Resolution.terminated:
          return HookType.onStop;
        default:
          throw new ScenarioPageHookUnknownError(result.resolution);
      }
    };
    Scenario2.prototype.executeHook = function(hookType) {
      var _a;
      return __awaiter(this, void 0, void 0, function() {
        var hook, _i, _b, action;
        return __generator(this, function(_c) {
          switch (_c.label) {
            case 0:
              hook = (_a = this.hooks) === null || _a === void 0 ? void 0 : _a[hookType];
              if (!hook)
                return [2];
              _i = 0, _b = hook.actions;
              _c.label = 1;
            case 1:
              if (!(_i < _b.length))
                return [3, 4];
              action = _b[_i];
              return [4, action.execute()];
            case 2:
              _c.sent();
              _c.label = 3;
            case 3:
              _i++;
              return [3, 1];
            case 4:
              return [2];
          }
        });
      });
    };
    Scenario2.prototype.disposeActions = function() {
      this.scenarioPages.forEach(function(page) {
        return page.disposeActions();
      });
    };
    Scenario2.prototype.disposeHookActions = function(hook) {
      hook.actions.forEach(function(action) {
        return action.dispose();
      });
    };
    Scenario2.prototype.dispose = function() {
      this.scenarioPages.forEach(function(page) {
        return page.dispose();
      });
      if (this.hooks)
        Object.values(this.hooks).forEach(this.disposeHookActions);
      for (var key in this)
        if (this.hasOwnProperty(key))
          delete this[key];
    };
    Scenario2.prototype.executePages = function() {
      return __awaiter(this, void 0, void 0, function() {
        var pageResult, _i, _a, page, error_1;
        return __generator(this, function(_b) {
          switch (_b.label) {
            case 0:
              if (this.scenarioPages.length === 0)
                return [2, this.handleSuccess(new ScenarioResult(this.name, Resolution.succeeded, ExecutionStack.getStack()))];
              _i = 0, _a = this.scenarioPages;
              _b.label = 1;
            case 1:
              if (!(_i < _a.length))
                return [3, 7];
              page = _a[_i];
              _b.label = 2;
            case 2:
              _b.trys.push([2, 4, , 5]);
              return [4, page.execute()];
            case 3:
              pageResult = _b.sent();
              return [3, 5];
            case 4:
              error_1 = _b.sent();
              return [2, this.handleError(error_1)];
            case 5:
              if (pageResult.resolution !== Resolution.succeeded)
                return [3, 7];
              _b.label = 6;
            case 6:
              _i++;
              return [3, 1];
            case 7:
              return [2, this.handleSuccess(new ScenarioResult(this.name, pageResult.resolution, ExecutionStack.getStack()))];
          }
        });
      });
    };
    Scenario2.prototype.handleSuccess = function(result) {
      return Promise.resolve(result);
    };
    Scenario2.prototype.handleError = function(error) {
      return Promise.reject(error);
    };
    return Scenario2;
  }();
  var ScenarioParser = function() {
    function ScenarioParser2() {
      this.invalidKeys = [];
    }
    ScenarioParser2.prototype.parse = function(scenarioData) {
      this.invalidKeys = [];
      this.sourceData = this.parseSourceData(scenarioData);
      if (!Validator.isObjectWithKeys(this.sourceData))
        this.throwInvalidSourceData();
      return this.parseScenario(this.sourceData);
    };
    ScenarioParser2.prototype.parseSourceData = function(data) {
      try {
        return Validator.isString(data) ? JSON.parse(data) : data;
      } catch (error) {
        this.throwInvalidSourceData();
      }
    };
    ScenarioParser2.prototype.pushInvalidKey = function(key, description) {
      this.invalidKeys.push({ key, description });
    };
    ScenarioParser2.prototype.throwInvalidSourceData = function() {
      this.pushInvalidKey("source-data", "The Scenario is not valid JSON or an Object.");
      this.throwHandledError();
    };
    ScenarioParser2.prototype.throwHandledError = function(scenarioName) {
      if (scenarioName === void 0) {
        scenarioName = "Unknown";
      }
      this.sourceData = void 0;
      throw new ParserError(scenarioName, this.invalidKeys);
    };
    return ScenarioParser2;
  }();
  var PrivacyScenarioParser = function(_super) {
    __extends(PrivacyScenarioParser2, _super);
    function PrivacyScenarioParser2(pageParser, hooksParser) {
      if (pageParser === void 0) {
        pageParser = new PrivacyPageParser();
      }
      if (hooksParser === void 0) {
        hooksParser = new PrivacyHooksParser();
      }
      var _this = _super.call(this) || this;
      _this.pageParser = pageParser;
      _this.hooksParser = hooksParser;
      return _this;
    }
    PrivacyScenarioParser2.prototype.parseScenario = function(scenarioData) {
      var name = scenarioData.name, pages = scenarioData.pages, hooks = scenarioData.hooks;
      this.validateScenarioName(name);
      var parsedPages = this.getParsedPages(pages);
      var parsedHooks = this.hooksParser.parse(hooks);
      if (this.invalidKeys.length)
        this.throwHandledError(name);
      return new Scenario(name, parsedPages, parsedHooks);
    };
    PrivacyScenarioParser2.prototype.validateScenarioName = function(name) {
      if (!Validator.nonEmptyString(name))
        this.pushInvalidKey(PrivacyScenarioKeys.name, "The Scenario name was either not provided or the value is valid.");
    };
    PrivacyScenarioParser2.prototype.getParsedPages = function(pages) {
      var _this = this;
      if (!Validator.nonEmptyArray(pages)) {
        this.pushInvalidKey(PrivacyScenarioKeys.pages, "The Scenario pages are either not provided or the value is valid.");
        return [];
      }
      var parsedPages = [];
      pages.forEach(function(page) {
        try {
          parsedPages.push(_this.pageParser.parse(page));
        } catch (error) {
          _this.handleParsePageError(error);
        }
      });
      return parsedPages;
    };
    PrivacyScenarioParser2.prototype.handleParsePageError = function(error) {
      if (error instanceof ParserInvalidPageTargetError)
        return this.pushInvalidKey(PrivacyPageKeys.target, error.message);
      if (error instanceof ParseActionsFormatError || error instanceof ParserInvalidActionsError)
        return this.pushInvalidKey(PrivacyPageKeys.actions, error.message);
      if (error instanceof ParserInvalidHooksError)
        return this.pushInvalidKey(PrivacyPageKeys.hooks, error.message);
      this.pushInvalidKey(PrivacyScenarioKeys.pages, error.message);
    };
    return PrivacyScenarioParser2;
  }(ScenarioParser);
  var MissingScenarioError = function(_super) {
    __extends(MissingScenarioError2, _super);
    function MissingScenarioError2(caller, methodName) {
      if (caller === void 0) {
        caller = "unknown";
      }
      if (methodName === void 0) {
        methodName = "unknown";
      }
      var _this = _super.call(this) || this;
      _this.caller = caller;
      _this.methodName = methodName;
      _this.message = "Scenario has not been initiated or it has been already disposed.";
      return _this;
    }
    Object.defineProperty(MissingScenarioError2.prototype, "errorDetails", {
      get: function() {
        return [{
          key: this.caller,
          description: 'Method "'.concat(this.methodName, `" couldn't be executed without the scenario`)
        }];
      },
      enumerable: false,
      configurable: true
    });
    return MissingScenarioError2;
  }(HandledError);
  var UncaughtExceptionError = function(_super) {
    __extends(UncaughtExceptionError2, _super);
    function UncaughtExceptionError2(failReason) {
      var _this = _super.call(this) || this;
      _this.failReason = failReason;
      _this.message = "An unhandled exception occurred.";
      return _this;
    }
    Object.defineProperty(UncaughtExceptionError2.prototype, "errorDetails", {
      get: function() {
        return [{
          key: this.failReason.name,
          description: this.failReason.message,
          failReason: this.failReason
        }];
      },
      enumerable: false,
      configurable: true
    });
    return UncaughtExceptionError2;
  }(HandledError);
  var Runner = function() {
    function Runner2(parser) {
      this.parser = parser;
      this.eventEmitter = eventEmitter;
    }
    Runner2.prototype.initiateScenario = function(scenarioData) {
      return __awaiter(this, void 0, void 0, function() {
        var error_1;
        return __generator(this, function(_a) {
          switch (_a.label) {
            case 0:
              _a.trys.push([0, 2, , 4]);
              return [4, this.disposeScenario()];
            case 1:
              _a.sent();
              this.scenario = this.getParsedScenario(scenarioData);
              return [3, 4];
            case 2:
              error_1 = _a.sent();
              return [4, this.handleError(error_1)];
            case 3:
              _a.sent();
              return [3, 4];
            case 4:
              return [2];
          }
        });
      });
    };
    Runner2.prototype.start = function() {
      return __awaiter(this, void 0, void 0, function() {
        var result, error_2;
        return __generator(this, function(_a) {
          switch (_a.label) {
            case 0:
              if (!this.scenario)
                return [2, this.handleError(new MissingScenarioError(this.constructor.name, "start"))];
              _a.label = 1;
            case 1:
              _a.trys.push([1, 3, , 4]);
              return [4, this.scenario.run()];
            case 2:
              result = _a.sent();
              return [2, this.handleSuccess(result)];
            case 3:
              error_2 = _a.sent();
              return [2, this.handleError(error_2)];
            case 4:
              return [2];
          }
        });
      });
    };
    Runner2.prototype.stop = function() {
      return __awaiter(this, void 0, void 0, function() {
        var result;
        return __generator(this, function(_a) {
          if (!this.scenario)
            return [2, this.handleError(new MissingScenarioError(this.constructor.name, "stop"))];
          this.scenario.disposeActions();
          result = new ScenarioResult(this.scenario.name, Resolution.terminated, ExecutionStack.getStack());
          return [2, this.handleSuccess(result)];
        });
      });
    };
    Runner2.prototype.handleSuccess = function(result) {
      var _a, _b;
      return __awaiter(this, void 0, void 0, function() {
        var error_3;
        return __generator(this, function(_c) {
          switch (_c.label) {
            case 0:
              _c.trys.push([0, 2, 4, 6]);
              return [4, (_a = this.scenario) === null || _a === void 0 ? void 0 : _a.executeHook(this.scenario.getHookType(result))];
            case 1:
              _c.sent();
              return [3, 6];
            case 2:
              error_3 = _c.sent();
              return [4, this.handleError(error_3)];
            case 3:
              _c.sent();
              return [3, 6];
            case 4:
              return [4, (_b = this.scenario) === null || _b === void 0 ? void 0 : _b.executeHook(HookType.onDisposed)];
            case 5:
              _c.sent();
              return [7];
            case 6:
              return [4, this.disposeScenario()];
            case 7:
              _c.sent();
              return [2, Promise.resolve(result)];
          }
        });
      });
    };
    Runner2.prototype.handleError = function(error) {
      var _a;
      return __awaiter(this, void 0, void 0, function() {
        var handledError, result;
        return __generator(this, function(_b) {
          switch (_b.label) {
            case 0:
              handledError = error instanceof HandledError ? error : new UncaughtExceptionError(error);
              result = ScenarioResult.buildFailedResult(this.scenario, handledError, ExecutionStack.getStack());
              this.eventEmitter.emit(ScenarioEvent.onError, result);
              return [4, (_a = this.scenario) === null || _a === void 0 ? void 0 : _a.executeHook(HookType.onFailed)];
            case 1:
              _b.sent();
              return [2, Promise.reject(result)];
          }
        });
      });
    };
    Runner2.prototype.disposeScenario = function() {
      return __awaiter(this, void 0, void 0, function() {
        return __generator(this, function(_a) {
          switch (_a.label) {
            case 0:
              if (!this.scenario)
                return [2];
              return [4, this.scenario.dispose()];
            case 1:
              _a.sent();
              this.scenario = void 0;
              ExecutionStack.clearStack();
              return [2];
          }
        });
      });
    };
    Runner2.prototype.getParsedScenario = function(scenario) {
      return this.parser.parse(scenario);
    };
    return Runner2;
  }();
  var ScenarioLogger = function() {
    function ScenarioLogger2() {
    }
    ScenarioLogger2.logResult = function(result) {
      switch (result.resolution) {
        case Resolution.failed:
          return this.logFailedResult(result);
        default:
          console.log(result);
      }
    };
    ScenarioLogger2.logFailedResult = function(result) {
      var error = result.error, scenarioName = result.scenarioName;
      var label = "".concat(scenarioName, " - ").concat(error === null || error === void 0 ? void 0 : error.name, ": ").concat(error === null || error === void 0 ? void 0 : error.message);
      console.groupCollapsed("%c ! %c ".concat(label, " "), this.errorLabelStyle, this.errorBodyStyle);
      (error === null || error === void 0 ? void 0 : error.details) && this.logErrorDetails(error.details);
      console.groupEnd();
    };
    ScenarioLogger2.logErrorDetails = function(details) {
      var _this = this;
      details.forEach(function(detail) {
        return detail.failReason ? _this.logErrorFailReason(detail) : _this.logErrorMessage(detail.key, detail.description);
      });
    };
    ScenarioLogger2.logErrorFailReason = function(detail) {
      var _a;
      console.groupCollapsed("%c ".concat(detail.key, " %c ").concat(detail.description, " "), this.errorLabelStyle, this.errorBodyStyle);
      console.log("%c ".concat((_a = detail.failReason) === null || _a === void 0 ? void 0 : _a.stack, " "), this.errorBodyStyle);
      console.groupEnd();
    };
    ScenarioLogger2.logErrorMessage = function(label, body) {
      console.log("%c ".concat(label, " %c ").concat(body, " "), this.errorLabelStyle, this.errorBodyStyle);
    };
    ScenarioLogger2.errorLabelStyle = "background: #d5322a; color: #fff; padding: 2px; font-weight: bold";
    ScenarioLogger2.errorBodyStyle = "background: #fff0f0; color: #d5322a; padding: 2px;";
    return ScenarioLogger2;
  }();

  // src/core/observable/observer/Observer.ts
  var Observer = class {
    constructor(callback, observable) {
      this.callback = callback;
      this.observable = observable;
    }
    subscribe() {
      this.observable.subscribe(this);
    }
    unsubscribe() {
      this.observable.unsubscribe(this);
    }
  };

  // src/core/observable/Observable.ts
  var Observable = class {
    constructor() {
      this.observers = [];
    }
    subscribe(observer) {
      if (this.observers.includes(observer))
        return;
      this.observers.push(observer);
    }
    unsubscribe(observer) {
      this.observers = this.observers.filter((o) => o !== observer);
    }
    notify(...args) {
      this.observers.forEach((observer) => this.notifyObserver(observer, ...args));
    }
  };

  // src/core/messages/observable/MessageObservable.ts
  var MessageObservable = class extends Observable {
    constructor() {
      super();
      chrome.runtime.onMessage.addListener(this.notify.bind(this));
    }
    notify(message, sender, sendResponse) {
      return this.observers.some((observer) => this.notifyObserver(observer, message, sender, sendResponse));
    }
    notifyObserver(observer, message, sender, sendResponse) {
      if (observer.messageName !== message.name)
        return false;
      return observer.callback(message.body, sendResponse, sender) === true;
    }
  };

  // src/core/messages/observable/observer/MessageObserver.ts
  var MessageObserver = class extends Observer {
    constructor(messageName, callback, observable = new MessageObservable()) {
      super(callback, observable);
      this.messageName = messageName;
    }
  };

  // src/modules/cookieConsent/client/runner/actions/CookieIFrameMessageAction.ts
  var CookieIFrameMessageAction = class extends ActionBase {
    constructor(data) {
      super();
      this.data = data;
    }
    get cookieScenarioParams() {
      const { type, variant } = this.data;
      return { scenario: type, variant };
    }
    execute() {
      return new Promise((resolve, reject) => {
        this.sendMessage();
        this.addMessageListener(resolve);
        this.createTimeout(reject);
      });
    }
    disposeTimer() {
      if (this.timer)
        clearTimeout(this.timer);
      this.timer = null;
    }
    dispose() {
      this.disposeTimer();
      super.dispose();
    }
    createTimeout(reject) {
      this.timer = setTimeout(() => reject(new Error(`CookieFrameAction didn't get response within ${this.data.timeout}ms`)), this.data.timeout);
    }
    sendMessage() {
      const cookieFrameData = {
        detectionRules: this.data["detection-rules"],
        params: this.cookieScenarioParams
      };
      new ClientMessageQuery("cookieManager.runFrameScenario" /* RUN_FRAME_SCENARIO */, cookieFrameData).execute();
    }
    addMessageListener(resolve) {
      const observer = new MessageObserver("cookieManager.frameScenarioFinished" /* FRAME_SCENARIO_FINISHED */, (data) => {
        resolve(new ActionResult(data.resolution));
      });
      observer.subscribe();
    }
  };
  CookieIFrameMessageAction.event = "cookie-iframe-message";

  // src/modules/cookieConsent/client/runner/parsers/CookieIFrameMessageActionParser.ts
  var CookieIFrameMessageActionParser = class extends GenericActionParserBase {
    parse(action) {
      if (this.validateType(action.type) && this.validateVariant(action.variant) && this.validateDetectionRules(action["detection-rules"]))
        return new CookieIFrameMessageAction(action);
      this.throwParseError(CookieIFrameMessageAction.event);
    }
    validateDetectionRules(rules) {
      return Validator.nonEmptyArray(rules) && rules.every((rule) => this.validateDetectionRule(rule));
    }
    validateDetectionRule(rule) {
      return this.validateType(rule.type) && this.validateDetectors(rule.detectors);
    }
    validateDetectors(detectors) {
      return Validator.nonEmptyArray(detectors) && detectors.every((detector) => this.validateDetector(detector));
    }
    validateDetector(detector) {
      return Validator.nonEmptyString(detector.variant) && this.validateSelectors(detector.selectors);
    }
    validateSelectors(selectors) {
      return Validator.nonEmptyArray(selectors) && selectors.every((selector) => Validator.nonEmptyString(selector));
    }
    validateType(type) {
      return Validator.nonEmptyString(type);
    }
    validateVariant(variant) {
      return Validator.nonEmptyString(variant);
    }
  };

  // src/modules/cookieConsent/client/runner/actions/ValidateCookieAction.ts
  var ValidateCookieAction = class extends ActionBase {
    constructor(data) {
      super();
      this.data = data;
    }
    get cookies() {
      return document.cookie.split(";");
    }
    execute() {
      const found = this.cookies.some((name) => name.indexOf(this.data.cookie) >= 0);
      return this.handleSuccess(found ? Resolution.succeeded : Resolution.failed);
    }
  };
  ValidateCookieAction.event = "validate-cookie-action";

  // src/modules/cookieConsent/client/runner/actions/QueryBulkClickAction.ts
  var QueryBulkClickAction = class extends BulkClickAction {
    constructor(queryString) {
      super(queryString);
    }
    getNodes(queryString, parent) {
      return document.querySelectorAll(queryString);
    }
  };

  // src/modules/cookieConsent/client/runner/parsers/CookieBulkClickActionParser.ts
  var CookieBulkClickActionParser = class extends GenericActionParserBase {
    parse(action) {
      if (!action.querySelector)
        return new BulkClickActionParser().parse(action);
      if (!Validator.nonEmptyString(action.querySelector))
        throw this.throwParseError(BulkClickAction.event);
      return new QueryBulkClickAction(action.querySelector);
    }
  };

  // src/modules/cookieConsent/client/runner/parsers/ValidateCookieActionParser.ts
  var ValidateCookieActionParser = class extends GenericActionParserBase {
    parse(action) {
      if (!Validator.nonEmptyString(action.cookie))
        this.throwParseError(ValidateCookieAction.event);
      return new ValidateCookieAction(action);
    }
  };

  // src/modules/advisor/client/runner/actions/AdvisorNotificationAction.ts
  var AdvisorNotificationAction = class extends NotificationAction {
    buildComponent() {
      return new AdvisorNotificationComponent(this.content, this.className);
    }
  };
  AdvisorNotificationAction.event = "aos-notification";
  var AdvisorNotificationComponent = class extends NotificationComponent {
    render() {
      super.render();
      const openPreferencesElements = [...document.querySelectorAll("[data-aos-action]")];
      openPreferencesElements.forEach((element) => {
        this.addDomListener(element, "click", () => this.onClick(element.dataset.aosAction));
      });
    }
    onClick(action) {
      eventEmitter.emit(action);
    }
  };

  // node_modules/tsyringe/dist/esm5/types/lifecycle.js
  var Lifecycle;
  (function(Lifecycle2) {
    Lifecycle2[Lifecycle2["Transient"] = 0] = "Transient";
    Lifecycle2[Lifecycle2["Singleton"] = 1] = "Singleton";
    Lifecycle2[Lifecycle2["ResolutionScoped"] = 2] = "ResolutionScoped";
    Lifecycle2[Lifecycle2["ContainerScoped"] = 3] = "ContainerScoped";
  })(Lifecycle || (Lifecycle = {}));
  var lifecycle_default = Lifecycle;

  // node_modules/tslib/modules/index.js
  var import_tslib = __toESM(require_tslib(), 1);
  var {
    __extends: __extends2,
    __assign: __assign2,
    __rest,
    __decorate,
    __param,
    __metadata,
    __awaiter: __awaiter2,
    __generator: __generator2,
    __exportStar,
    __createBinding,
    __values: __values2,
    __read,
    __spread,
    __spreadArrays,
    __await,
    __asyncGenerator,
    __asyncDelegator,
    __asyncValues: __asyncValues2,
    __makeTemplateObject,
    __importStar,
    __importDefault,
    __classPrivateFieldGet,
    __classPrivateFieldSet
  } = import_tslib.default;

  // node_modules/tsyringe/dist/esm5/providers/class-provider.js
  function isClassProvider(provider) {
    return !!provider.useClass;
  }

  // node_modules/tsyringe/dist/esm5/providers/factory-provider.js
  function isFactoryProvider(provider) {
    return !!provider.useFactory;
  }

  // node_modules/tsyringe/dist/esm5/lazy-helpers.js
  var DelayedConstructor = function() {
    function DelayedConstructor2(wrap) {
      this.wrap = wrap;
      this.reflectMethods = [
        "get",
        "getPrototypeOf",
        "setPrototypeOf",
        "getOwnPropertyDescriptor",
        "defineProperty",
        "has",
        "set",
        "deleteProperty",
        "apply",
        "construct",
        "ownKeys"
      ];
    }
    DelayedConstructor2.prototype.createProxy = function(createObject) {
      var _this = this;
      var target = {};
      var init = false;
      var value;
      var delayedObject = function() {
        if (!init) {
          value = createObject(_this.wrap());
          init = true;
        }
        return value;
      };
      return new Proxy(target, this.createHandler(delayedObject));
    };
    DelayedConstructor2.prototype.createHandler = function(delayedObject) {
      var handler = {};
      var install = function(name) {
        handler[name] = function() {
          var args = [];
          for (var _i = 0; _i < arguments.length; _i++) {
            args[_i] = arguments[_i];
          }
          args[0] = delayedObject();
          var method = Reflect[name];
          return method.apply(void 0, __spread(args));
        };
      };
      this.reflectMethods.forEach(install);
      return handler;
    };
    return DelayedConstructor2;
  }();

  // node_modules/tsyringe/dist/esm5/providers/injection-token.js
  function isNormalToken(token) {
    return typeof token === "string" || typeof token === "symbol";
  }
  function isTokenDescriptor(descriptor) {
    return typeof descriptor === "object" && "token" in descriptor && "multiple" in descriptor;
  }
  function isTransformDescriptor(descriptor) {
    return typeof descriptor === "object" && "token" in descriptor && "transform" in descriptor;
  }
  function isConstructorToken(token) {
    return typeof token === "function" || token instanceof DelayedConstructor;
  }

  // node_modules/tsyringe/dist/esm5/providers/token-provider.js
  function isTokenProvider(provider) {
    return !!provider.useToken;
  }

  // node_modules/tsyringe/dist/esm5/providers/value-provider.js
  function isValueProvider(provider) {
    return provider.useValue != void 0;
  }

  // node_modules/tsyringe/dist/esm5/providers/provider.js
  function isProvider(provider) {
    return isClassProvider(provider) || isValueProvider(provider) || isTokenProvider(provider) || isFactoryProvider(provider);
  }

  // node_modules/tsyringe/dist/esm5/registry-base.js
  var RegistryBase = function() {
    function RegistryBase2() {
      this._registryMap = /* @__PURE__ */ new Map();
    }
    RegistryBase2.prototype.entries = function() {
      return this._registryMap.entries();
    };
    RegistryBase2.prototype.getAll = function(key) {
      this.ensure(key);
      return this._registryMap.get(key);
    };
    RegistryBase2.prototype.get = function(key) {
      this.ensure(key);
      var value = this._registryMap.get(key);
      return value[value.length - 1] || null;
    };
    RegistryBase2.prototype.set = function(key, value) {
      this.ensure(key);
      this._registryMap.get(key).push(value);
    };
    RegistryBase2.prototype.setAll = function(key, value) {
      this._registryMap.set(key, value);
    };
    RegistryBase2.prototype.has = function(key) {
      this.ensure(key);
      return this._registryMap.get(key).length > 0;
    };
    RegistryBase2.prototype.clear = function() {
      this._registryMap.clear();
    };
    RegistryBase2.prototype.ensure = function(key) {
      if (!this._registryMap.has(key)) {
        this._registryMap.set(key, []);
      }
    };
    return RegistryBase2;
  }();
  var registry_base_default = RegistryBase;

  // node_modules/tsyringe/dist/esm5/registry.js
  var Registry = function(_super) {
    __extends2(Registry2, _super);
    function Registry2() {
      return _super !== null && _super.apply(this, arguments) || this;
    }
    return Registry2;
  }(registry_base_default);
  var registry_default = Registry;

  // node_modules/tsyringe/dist/esm5/resolution-context.js
  var ResolutionContext = function() {
    function ResolutionContext2() {
      this.scopedResolutions = /* @__PURE__ */ new Map();
    }
    return ResolutionContext2;
  }();
  var resolution_context_default = ResolutionContext;

  // node_modules/tsyringe/dist/esm5/error-helpers.js
  function formatDependency(params, idx) {
    if (params === null) {
      return "at position #" + idx;
    }
    var argName = params.split(",")[idx].trim();
    return '"' + argName + '" at position #' + idx;
  }
  function composeErrorMessage(msg, e, indent) {
    if (indent === void 0) {
      indent = "    ";
    }
    return __spread([msg], e.message.split("\n").map(function(l) {
      return indent + l;
    })).join("\n");
  }
  function formatErrorCtor(ctor, paramIdx, error) {
    var _a = __read(ctor.toString().match(/constructor\(([\w, ]+)\)/) || [], 2), _b = _a[1], params = _b === void 0 ? null : _b;
    var dep = formatDependency(params, paramIdx);
    return composeErrorMessage("Cannot inject the dependency " + dep + ' of "' + ctor.name + '" constructor. Reason:', error);
  }

  // node_modules/tsyringe/dist/esm5/types/disposable.js
  function isDisposable(value) {
    if (typeof value.dispose !== "function")
      return false;
    var disposeFun = value.dispose;
    if (disposeFun.length > 0) {
      return false;
    }
    return true;
  }

  // node_modules/tsyringe/dist/esm5/interceptors.js
  var PreResolutionInterceptors = function(_super) {
    __extends2(PreResolutionInterceptors2, _super);
    function PreResolutionInterceptors2() {
      return _super !== null && _super.apply(this, arguments) || this;
    }
    return PreResolutionInterceptors2;
  }(registry_base_default);
  var PostResolutionInterceptors = function(_super) {
    __extends2(PostResolutionInterceptors2, _super);
    function PostResolutionInterceptors2() {
      return _super !== null && _super.apply(this, arguments) || this;
    }
    return PostResolutionInterceptors2;
  }(registry_base_default);
  var Interceptors = function() {
    function Interceptors2() {
      this.preResolution = new PreResolutionInterceptors();
      this.postResolution = new PostResolutionInterceptors();
    }
    return Interceptors2;
  }();
  var interceptors_default = Interceptors;

  // node_modules/tsyringe/dist/esm5/dependency-container.js
  var typeInfo = /* @__PURE__ */ new Map();
  var InternalDependencyContainer = function() {
    function InternalDependencyContainer2(parent) {
      this.parent = parent;
      this._registry = new registry_default();
      this.interceptors = new interceptors_default();
      this.disposed = false;
      this.disposables = /* @__PURE__ */ new Set();
    }
    InternalDependencyContainer2.prototype.register = function(token, providerOrConstructor, options) {
      if (options === void 0) {
        options = { lifecycle: lifecycle_default.Transient };
      }
      this.ensureNotDisposed();
      var provider;
      if (!isProvider(providerOrConstructor)) {
        provider = { useClass: providerOrConstructor };
      } else {
        provider = providerOrConstructor;
      }
      if (isTokenProvider(provider)) {
        var path = [token];
        var tokenProvider = provider;
        while (tokenProvider != null) {
          var currentToken = tokenProvider.useToken;
          if (path.includes(currentToken)) {
            throw new Error("Token registration cycle detected! " + __spread(path, [currentToken]).join(" -> "));
          }
          path.push(currentToken);
          var registration = this._registry.get(currentToken);
          if (registration && isTokenProvider(registration.provider)) {
            tokenProvider = registration.provider;
          } else {
            tokenProvider = null;
          }
        }
      }
      if (options.lifecycle === lifecycle_default.Singleton || options.lifecycle == lifecycle_default.ContainerScoped || options.lifecycle == lifecycle_default.ResolutionScoped) {
        if (isValueProvider(provider) || isFactoryProvider(provider)) {
          throw new Error('Cannot use lifecycle "' + lifecycle_default[options.lifecycle] + '" with ValueProviders or FactoryProviders');
        }
      }
      this._registry.set(token, { provider, options });
      return this;
    };
    InternalDependencyContainer2.prototype.registerType = function(from, to) {
      this.ensureNotDisposed();
      if (isNormalToken(to)) {
        return this.register(from, {
          useToken: to
        });
      }
      return this.register(from, {
        useClass: to
      });
    };
    InternalDependencyContainer2.prototype.registerInstance = function(token, instance2) {
      this.ensureNotDisposed();
      return this.register(token, {
        useValue: instance2
      });
    };
    InternalDependencyContainer2.prototype.registerSingleton = function(from, to) {
      this.ensureNotDisposed();
      if (isNormalToken(from)) {
        if (isNormalToken(to)) {
          return this.register(from, {
            useToken: to
          }, { lifecycle: lifecycle_default.Singleton });
        } else if (to) {
          return this.register(from, {
            useClass: to
          }, { lifecycle: lifecycle_default.Singleton });
        }
        throw new Error('Cannot register a type name as a singleton without a "to" token');
      }
      var useClass = from;
      if (to && !isNormalToken(to)) {
        useClass = to;
      }
      return this.register(from, {
        useClass
      }, { lifecycle: lifecycle_default.Singleton });
    };
    InternalDependencyContainer2.prototype.resolve = function(token, context) {
      if (context === void 0) {
        context = new resolution_context_default();
      }
      this.ensureNotDisposed();
      var registration = this.getRegistration(token);
      if (!registration && isNormalToken(token)) {
        throw new Error('Attempted to resolve unregistered dependency token: "' + token.toString() + '"');
      }
      this.executePreResolutionInterceptor(token, "Single");
      if (registration) {
        var result = this.resolveRegistration(registration, context);
        this.executePostResolutionInterceptor(token, result, "Single");
        return result;
      }
      if (isConstructorToken(token)) {
        var result = this.construct(token, context);
        this.executePostResolutionInterceptor(token, result, "Single");
        return result;
      }
      throw new Error("Attempted to construct an undefined constructor. Could mean a circular dependency problem. Try using `delay` function.");
    };
    InternalDependencyContainer2.prototype.executePreResolutionInterceptor = function(token, resolutionType) {
      var e_1, _a;
      if (this.interceptors.preResolution.has(token)) {
        var remainingInterceptors = [];
        try {
          for (var _b = __values2(this.interceptors.preResolution.getAll(token)), _c = _b.next(); !_c.done; _c = _b.next()) {
            var interceptor = _c.value;
            if (interceptor.options.frequency != "Once") {
              remainingInterceptors.push(interceptor);
            }
            interceptor.callback(token, resolutionType);
          }
        } catch (e_1_1) {
          e_1 = { error: e_1_1 };
        } finally {
          try {
            if (_c && !_c.done && (_a = _b.return))
              _a.call(_b);
          } finally {
            if (e_1)
              throw e_1.error;
          }
        }
        this.interceptors.preResolution.setAll(token, remainingInterceptors);
      }
    };
    InternalDependencyContainer2.prototype.executePostResolutionInterceptor = function(token, result, resolutionType) {
      var e_2, _a;
      if (this.interceptors.postResolution.has(token)) {
        var remainingInterceptors = [];
        try {
          for (var _b = __values2(this.interceptors.postResolution.getAll(token)), _c = _b.next(); !_c.done; _c = _b.next()) {
            var interceptor = _c.value;
            if (interceptor.options.frequency != "Once") {
              remainingInterceptors.push(interceptor);
            }
            interceptor.callback(token, result, resolutionType);
          }
        } catch (e_2_1) {
          e_2 = { error: e_2_1 };
        } finally {
          try {
            if (_c && !_c.done && (_a = _b.return))
              _a.call(_b);
          } finally {
            if (e_2)
              throw e_2.error;
          }
        }
        this.interceptors.postResolution.setAll(token, remainingInterceptors);
      }
    };
    InternalDependencyContainer2.prototype.resolveRegistration = function(registration, context) {
      this.ensureNotDisposed();
      if (registration.options.lifecycle === lifecycle_default.ResolutionScoped && context.scopedResolutions.has(registration)) {
        return context.scopedResolutions.get(registration);
      }
      var isSingleton = registration.options.lifecycle === lifecycle_default.Singleton;
      var isContainerScoped = registration.options.lifecycle === lifecycle_default.ContainerScoped;
      var returnInstance = isSingleton || isContainerScoped;
      var resolved;
      if (isValueProvider(registration.provider)) {
        resolved = registration.provider.useValue;
      } else if (isTokenProvider(registration.provider)) {
        resolved = returnInstance ? registration.instance || (registration.instance = this.resolve(registration.provider.useToken, context)) : this.resolve(registration.provider.useToken, context);
      } else if (isClassProvider(registration.provider)) {
        resolved = returnInstance ? registration.instance || (registration.instance = this.construct(registration.provider.useClass, context)) : this.construct(registration.provider.useClass, context);
      } else if (isFactoryProvider(registration.provider)) {
        resolved = registration.provider.useFactory(this);
      } else {
        resolved = this.construct(registration.provider, context);
      }
      if (registration.options.lifecycle === lifecycle_default.ResolutionScoped) {
        context.scopedResolutions.set(registration, resolved);
      }
      return resolved;
    };
    InternalDependencyContainer2.prototype.resolveAll = function(token, context) {
      var _this = this;
      if (context === void 0) {
        context = new resolution_context_default();
      }
      this.ensureNotDisposed();
      var registrations = this.getAllRegistrations(token);
      if (!registrations && isNormalToken(token)) {
        throw new Error('Attempted to resolve unregistered dependency token: "' + token.toString() + '"');
      }
      this.executePreResolutionInterceptor(token, "All");
      if (registrations) {
        var result_1 = registrations.map(function(item) {
          return _this.resolveRegistration(item, context);
        });
        this.executePostResolutionInterceptor(token, result_1, "All");
        return result_1;
      }
      var result = [this.construct(token, context)];
      this.executePostResolutionInterceptor(token, result, "All");
      return result;
    };
    InternalDependencyContainer2.prototype.isRegistered = function(token, recursive) {
      if (recursive === void 0) {
        recursive = false;
      }
      this.ensureNotDisposed();
      return this._registry.has(token) || recursive && (this.parent || false) && this.parent.isRegistered(token, true);
    };
    InternalDependencyContainer2.prototype.reset = function() {
      this.ensureNotDisposed();
      this._registry.clear();
      this.interceptors.preResolution.clear();
      this.interceptors.postResolution.clear();
    };
    InternalDependencyContainer2.prototype.clearInstances = function() {
      var e_3, _a;
      this.ensureNotDisposed();
      try {
        for (var _b = __values2(this._registry.entries()), _c = _b.next(); !_c.done; _c = _b.next()) {
          var _d = __read(_c.value, 2), token = _d[0], registrations = _d[1];
          this._registry.setAll(token, registrations.filter(function(registration) {
            return !isValueProvider(registration.provider);
          }).map(function(registration) {
            registration.instance = void 0;
            return registration;
          }));
        }
      } catch (e_3_1) {
        e_3 = { error: e_3_1 };
      } finally {
        try {
          if (_c && !_c.done && (_a = _b.return))
            _a.call(_b);
        } finally {
          if (e_3)
            throw e_3.error;
        }
      }
    };
    InternalDependencyContainer2.prototype.createChildContainer = function() {
      var e_4, _a;
      this.ensureNotDisposed();
      var childContainer = new InternalDependencyContainer2(this);
      try {
        for (var _b = __values2(this._registry.entries()), _c = _b.next(); !_c.done; _c = _b.next()) {
          var _d = __read(_c.value, 2), token = _d[0], registrations = _d[1];
          if (registrations.some(function(_a2) {
            var options = _a2.options;
            return options.lifecycle === lifecycle_default.ContainerScoped;
          })) {
            childContainer._registry.setAll(token, registrations.map(function(registration) {
              if (registration.options.lifecycle === lifecycle_default.ContainerScoped) {
                return {
                  provider: registration.provider,
                  options: registration.options
                };
              }
              return registration;
            }));
          }
        }
      } catch (e_4_1) {
        e_4 = { error: e_4_1 };
      } finally {
        try {
          if (_c && !_c.done && (_a = _b.return))
            _a.call(_b);
        } finally {
          if (e_4)
            throw e_4.error;
        }
      }
      return childContainer;
    };
    InternalDependencyContainer2.prototype.beforeResolution = function(token, callback, options) {
      if (options === void 0) {
        options = { frequency: "Always" };
      }
      this.interceptors.preResolution.set(token, {
        callback,
        options
      });
    };
    InternalDependencyContainer2.prototype.afterResolution = function(token, callback, options) {
      if (options === void 0) {
        options = { frequency: "Always" };
      }
      this.interceptors.postResolution.set(token, {
        callback,
        options
      });
    };
    InternalDependencyContainer2.prototype.dispose = function() {
      return __awaiter2(this, void 0, void 0, function() {
        var promises;
        return __generator2(this, function(_a) {
          switch (_a.label) {
            case 0:
              this.disposed = true;
              promises = [];
              this.disposables.forEach(function(disposable) {
                var maybePromise = disposable.dispose();
                if (maybePromise) {
                  promises.push(maybePromise);
                }
              });
              return [4, Promise.all(promises)];
            case 1:
              _a.sent();
              return [2];
          }
        });
      });
    };
    InternalDependencyContainer2.prototype.getRegistration = function(token) {
      if (this.isRegistered(token)) {
        return this._registry.get(token);
      }
      if (this.parent) {
        return this.parent.getRegistration(token);
      }
      return null;
    };
    InternalDependencyContainer2.prototype.getAllRegistrations = function(token) {
      if (this.isRegistered(token)) {
        return this._registry.getAll(token);
      }
      if (this.parent) {
        return this.parent.getAllRegistrations(token);
      }
      return null;
    };
    InternalDependencyContainer2.prototype.construct = function(ctor, context) {
      var _this = this;
      if (ctor instanceof DelayedConstructor) {
        return ctor.createProxy(function(target) {
          return _this.resolve(target, context);
        });
      }
      var instance2 = function() {
        var paramInfo = typeInfo.get(ctor);
        if (!paramInfo || paramInfo.length === 0) {
          if (ctor.length === 0) {
            return new ctor();
          } else {
            throw new Error('TypeInfo not known for "' + ctor.name + '"');
          }
        }
        var params = paramInfo.map(_this.resolveParams(context, ctor));
        return new (ctor.bind.apply(ctor, __spread([void 0], params)))();
      }();
      if (isDisposable(instance2)) {
        this.disposables.add(instance2);
      }
      return instance2;
    };
    InternalDependencyContainer2.prototype.resolveParams = function(context, ctor) {
      var _this = this;
      return function(param, idx) {
        var _a, _b, _c;
        try {
          if (isTokenDescriptor(param)) {
            if (isTransformDescriptor(param)) {
              return param.multiple ? (_a = _this.resolve(param.transform)).transform.apply(_a, __spread([_this.resolveAll(param.token)], param.transformArgs)) : (_b = _this.resolve(param.transform)).transform.apply(_b, __spread([_this.resolve(param.token, context)], param.transformArgs));
            } else {
              return param.multiple ? _this.resolveAll(param.token) : _this.resolve(param.token, context);
            }
          } else if (isTransformDescriptor(param)) {
            return (_c = _this.resolve(param.transform, context)).transform.apply(_c, __spread([_this.resolve(param.token, context)], param.transformArgs));
          }
          return _this.resolve(param, context);
        } catch (e) {
          throw new Error(formatErrorCtor(ctor, idx, e));
        }
      };
    };
    InternalDependencyContainer2.prototype.ensureNotDisposed = function() {
      if (this.disposed) {
        throw new Error("This container has been disposed, you cannot interact with a disposed container");
      }
    };
    return InternalDependencyContainer2;
  }();
  var instance = new InternalDependencyContainer();

  // node_modules/tsyringe/dist/esm5/index.js
  if (typeof Reflect === "undefined" || !Reflect.getMetadata) {
    throw new Error(`tsyringe requires a reflect polyfill. Please add 'import "reflect-metadata"' to the top of your entry point.`);
  }

  // src/client/localization/ClientLocalization.ts
  var nls = (key, ...args) => {
    const library = instance.resolve("Localization" /* LOCALIZATION */);
    return library.translate(key, ...args);
  };
  var burgerTranslate = (key) => {
    const library = instance.resolve("Localization" /* LOCALIZATION */);
    return library.translateToLocale(key, "en" /* English */);
  };

  // src/modules/cookieConsent/client/runner/parsers/CookieNotificationActionParser.ts
  var CookieNotificationActionParser = class extends NotificationActionParser {
    parse(action) {
      if (!this.validateNotificationData(action))
        this.throwParseError(action.event);
      return this.getParsedNotificationAction(action);
    }
    parseHtmlContent(action) {
      if (!this.validateHtmlContent(action.componentData))
        throw new Error();
      const { label, heading, minutes, body, button, secondaryButton, badge, actionLink, illustration } = action.componentData;
      return `
			${this.renderOverlay(action)}

			<aside class='aos-notification'>
				<header>
					<h2>${nls(label)}</h2>
					<button class='close-icon'></button>
				</header>

				<div class='illustration ${illustration}'></div>

				<div class='component-body'>
					${this.renderBadge(badge, action.className, minutes)}
					${this.renderHeading(heading)}
					<p>${nls(body)}</p>
					${this.renderButtonWrap(button)}
					${this.renderSecondaryButtonWrap(secondaryButton)}
					${this.renderActionLink(actionLink, action.className)}
				</div>
			</aside>
		`;
    }
    renderOverlay(action) {
      return !action.hasOwnProperty("showOverlay") || action.showOverlay ? '<div class="aos-overlay"></div>' : "";
    }
    renderHeading(heading) {
      return heading ? `<h3>${nls(heading)}</h3>` : "";
    }
    renderButtonWrap(button) {
      if (!button)
        return "";
      const closeButton = button.isClose ? "close-button" : "";
      const className = button.className ? button.className : "";
      return `
			<div class='button-wrap'>
				<a 
					${button.href && `href=${button.href}`}
					${button.action && `data-aos-action=${button.action}`}
					class="${closeButton} ${className}">${nls(button.text)}</a>
			</div>
		`;
    }
    renderSecondaryButtonWrap(secondaryButton) {
      if (!secondaryButton)
        return "";
      const className = secondaryButton.className ? secondaryButton.className : "";
      return `
			<div class='button-wrap'>
				<a class='aos-secondary-button ${className}' 
					${secondaryButton.href && `href=${secondaryButton.href}`}
					${secondaryButton.action && `data-aos-action=${secondaryButton.action}`}
					>${nls(secondaryButton.text)}</a>
			</div>
		`;
    }
    renderBadge(badge, className, minutes) {
      if (!badge || !className.includes("trigger-notification"))
        return "";
      return `
			<span class='badge'>${nls("guides.notification.minutes", minutes)}</span>
		`;
    }
    renderActionLink(actionLink, className) {
      if (!actionLink || !className.includes("trigger-notification"))
        return "";
      return `
			<a class='a' data-aos-action='${actionLink.action}'>${nls(actionLink.text)}</a>
		`;
    }
    validateNotificationData(action) {
      return this.validateActionClassName(action);
    }
    getParsedNotificationAction(action) {
      try {
        const className = `aos-component aos-notification-component ${action.className || ""}`;
        const parsedConditions = this.parseResolveConditions(action.resolveConditions).concat(this.getCustomCloseConditions(action));
        const trackableContent = this.getTrackableContent(action.componentData);
        return new AdvisorNotificationAction(this.parseHtmlContent(action), className, parsedConditions, trackableContent);
      } catch (e) {
        console.error(e);
        this.throwParseError(action.event);
      }
    }
    getTrackableContent(data) {
      const { body, heading } = data;
      const translatedHeading = burgerTranslate(heading);
      const translatedBody = burgerTranslate(body);
      return `[${translatedHeading}] ${translatedBody}`;
    }
    getCustomCloseConditions(action) {
      const hasCloseButton = action.componentData.button && action.componentData.button.isClose;
      const classNames = !action.hasOwnProperty("showOverlay") || action.showOverlay ? ["close-icon", "aos-overlay"] : ["close-icon"];
      return classNames.map((name) => {
        const elements = [
          { xpath: `//div[contains(@class, "aos-component")]//*[@class="${name}"]`, multipleMatch: true }
        ];
        if (name === "close-icon" && hasCloseButton)
          elements.push({ xpath: '//div[contains(@class, "aos-component")]//*[contains(@class, "close-button")]', multipleMatch: true });
        return {
          elements,
          groupId: "scenario-closed"
        };
      });
    }
    validateHtmlContent(data) {
      const requiredValues = [data.label, data.body];
      if (!requiredValues.every((val) => Validator.isString(val)) || !this.validateButton(data) || !this.validateSecondaryButton(data) || !this.validateHeading(data) || !this.validateBadge(data) || !this.validateActionLink(data) || !this.validateIllustration(data))
        return false;
      return this.validateButton(data);
    }
    validateButton(data) {
      if (!data.hasOwnProperty("button"))
        return true;
      const button = data.button;
      return Validator.isString(button.text) || button.hasOwnProperty("href") && Validator.isString(button.href) || button.hasOwnProperty("action") && Validator.isString(button.action) || button.hasOwnProperty("classname") && Validator.isString(button.classname) || button.hasOwnProperty("isClose") && Validator.isBoolean(button.isClose);
    }
    validateSecondaryButton(data) {
      if (!data.hasOwnProperty("secondaryButton"))
        return true;
      const secondaryButton = data.secondaryButton;
      return Validator.isString(secondaryButton.text) || secondaryButton.hasOwnProperty("href") && Validator.isString(secondaryButton.href) || secondaryButton.hasOwnProperty("action") && Validator.isString(secondaryButton.action);
    }
    validateHeading(data) {
      return !data.hasOwnProperty("heading") || Validator.isString(data.heading);
    }
    validateBadge(data) {
      return !data.hasOwnProperty("badge") || Validator.isBoolean(data.badge);
    }
    validateActionLink(data) {
      if (!data.hasOwnProperty("actionLink"))
        return true;
      const link = data.actionLink;
      return Validator.isString(link.text) || Validator.isString(link.action);
    }
    validateIllustration(data) {
      return !data.hasOwnProperty("illustration") || Validator.isString(data.illustration);
    }
  };

  // src/modules/cookieConsent/client/runner/parsers/CookieActionParser.ts
  var CookieActionParser = class extends PrivacyActionParser {
    parseAction(action) {
      switch (action.event) {
        case CookieIFrameMessageAction.event:
          return new CookieIFrameMessageActionParser().parse(action);
        case ValidateCookieAction.event:
          return new ValidateCookieActionParser().parse(action);
        case BulkClickAction.event:
          return new CookieBulkClickActionParser().parse(action);
        case AdvisorNotificationAction.event:
          return new CookieNotificationActionParser().parse(action);
        default:
          return super.parseAction(action);
      }
    }
  };

  // src/modules/cookieConsent/client/runner/enums/CookieNotificationAction.ts
  var CookieNotificationAction = /* @__PURE__ */ ((CookieNotificationAction2) => {
    CookieNotificationAction2["ENABLE_COOKIE_MANAGER"] = "cookie.enable-cookie-manager";
    CookieNotificationAction2["HIDE_FOREVER"] = "cookie.hide-forever";
    CookieNotificationAction2["DISMISS"] = "cookie.dismiss-cookie-notification";
    CookieNotificationAction2["OPEN_PROMOTED_LINK"] = "cookie.openPromotedLink";
    return CookieNotificationAction2;
  })(CookieNotificationAction || {});

  // src/modules/cookieConsent/client/runner/CookieScenarioRunner.ts
  var CookieScenarioRunner = class {
    constructor(scenarioData) {
      this.scenarioData = scenarioData;
      this.runner = new Runner(this.getScenarioParser());
    }
    getScenarioParser() {
      const actionParser = new CookieActionParser();
      const privacyPageParser = new PrivacyPageParser(actionParser);
      return new PrivacyScenarioParser(privacyPageParser);
    }
    start() {
      return __async(this, null, function* () {
        this.registerBackgroundListeners();
        yield this.runner.initiateScenario(this.scenarioData);
        const result = yield this.runner.start();
        return Promise.resolve(result);
      });
    }
    registerBackgroundListeners() {
      [...Object.values(CookieNotificationAction)].forEach((eventName) => {
        this.runner.eventEmitter.addListener(eventName, (...args) => {
          const eventArgs = JSON.parse(JSON.stringify(args));
          new ClientMessageQuery(eventName, { eventArgs }).execute();
        });
      });
    }
  };

  // src/modules/cookieConsent/client/script/handler/CookieFrameHandler.ts
  var CookieFrameHandler = class extends CookieHandlerBase {
    constructor() {
      super();
      this.observer = new MessageObserver("cookieManager.runFrameScenario" /* RUN_FRAME_SCENARIO */, this.onRunFrameScenario.bind(this));
      this.observer.subscribe();
    }
    onRunFrameScenario(data) {
      this.runScenario(data.cookieFrameData);
    }
    runScenario(data) {
      return __async(this, null, function* () {
        try {
          const detectedScenario = yield new CookieDomWatcher(data.detectionRules).observe();
          const scenarioData = yield this.getScenario(__spreadProps(__spreadValues({}, data.params), { operation: detectedScenario.variant }));
          const result = yield new CookieScenarioRunner(JSON.stringify(scenarioData)).start();
          yield new ClientMessageQuery("cookieManager.frameScenarioFinished" /* FRAME_SCENARIO_FINISHED */, { resolution: result.resolution }).execute();
        } catch (e) {
          console.error(e);
        }
      });
    }
  };
  new CookieFrameHandler();
})();
/*! *****************************************************************************
Copyright (C) Microsoft. All rights reserved.
Licensed under the Apache License, Version 2.0 (the "License"); you may not use
this file except in compliance with the License. You may obtain a copy of the
License at http://www.apache.org/licenses/LICENSE-2.0

THIS CODE IS PROVIDED ON AN *AS IS* BASIS, WITHOUT WARRANTIES OR CONDITIONS OF ANY
KIND, EITHER EXPRESS OR IMPLIED, INCLUDING WITHOUT LIMITATION ANY IMPLIED
WARRANTIES OR CONDITIONS OF TITLE, FITNESS FOR A PARTICULAR PURPOSE,
MERCHANTABLITY OR NON-INFRINGEMENT.

See the Apache Version 2.0 License for specific language governing permissions
and limitations under the License.
***************************************************************************** */
/*! *****************************************************************************
Copyright (c) Microsoft Corporation.

Permission to use, copy, modify, and/or distribute this software for any
purpose with or without fee is hereby granted.

THE SOFTWARE IS PROVIDED "AS IS" AND THE AUTHOR DISCLAIMS ALL WARRANTIES WITH
REGARD TO THIS SOFTWARE INCLUDING ALL IMPLIED WARRANTIES OF MERCHANTABILITY
AND FITNESS. IN NO EVENT SHALL THE AUTHOR BE LIABLE FOR ANY SPECIAL, DIRECT,
INDIRECT, OR CONSEQUENTIAL DAMAGES OR ANY DAMAGES WHATSOEVER RESULTING FROM
LOSS OF USE, DATA OR PROFITS, WHETHER IN AN ACTION OF CONTRACT, NEGLIGENCE OR
OTHER TORTIOUS ACTION, ARISING OUT OF OR IN CONNECTION WITH THE USE OR
PERFORMANCE OF THIS SOFTWARE.
***************************************************************************** */
