// SYSTEM DESIGN CONCEPT: Abstract Factory Pattern
// This defines an interface for creating families of related objects (theme classes)
// without specifying their concrete classes.

export class ThemeFactory {
    getBackground() { throw new Error("Not implemented"); }
    getText() { throw new Error("Not implemented"); }
    getHeading() { throw new Error("Not implemented"); }
    getCardBackground() { throw new Error("Not implemented"); }
    getCardBorder() { throw new Error("Not implemented"); }
    getSecondaryButton() { throw new Error("Not implemented"); }
}

export class LightThemeFactory extends ThemeFactory {
    getBackground() { return "bg-slate-50"; }
    getText() { return "text-slate-500"; }
    getHeading() { return "text-slate-900"; }
    getCardBackground() { return "bg-white"; }
    getCardBorder() { return "border-slate-200"; }
    getSecondaryButton() { return "bg-white hover:bg-slate-50 text-slate-700 border border-slate-300"; }
}

export class DarkThemeFactory extends ThemeFactory {
    getBackground() { return "bg-slate-950"; }
    getText() { return "text-slate-400"; }
    getHeading() { return "text-white"; }
    getCardBackground() { return "bg-slate-900"; }
    getCardBorder() { return "border-slate-800"; }
    getSecondaryButton() { return "bg-slate-800 hover:bg-slate-700 text-slate-300 border border-slate-700 focus:ring-slate-500"; }
}
