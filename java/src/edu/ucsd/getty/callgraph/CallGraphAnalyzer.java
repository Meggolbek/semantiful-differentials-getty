package edu.ucsd.getty.callgraph;


import java.util.HashMap;
import java.util.HashSet;
import java.util.List;
import java.util.Map;
import java.util.Set;
import java.io.IOException;
import java.io.FileWriter;
import java.io.BufferedWriter;
import java.io.PrintWriter;

import org.apache.bcel.classfile.JavaClass;
import org.apache.bcel.classfile.Method;

import edu.ucsd.getty.visitors.InvocationInstallationBinVisitor;

/**
 * Construct call graph from class folders, zips and/or jars. 
 * The result(s) will be combined into one call graph.
 * 
 */

public class CallGraphAnalyzer {
	
	private String packagePrefix;
	private Set<String> allProjectMethods;
	public HashMap<String, Set<String>> classDependencies;
	public HashMap<String, Set<String>> typesToMethods;

	public CallGraphAnalyzer(String pkgPrefix) {
		this.packagePrefix = pkgPrefix;
		this.allProjectMethods = new HashSet<String>();
	}
	
	public CallGraphAnalyzer() {
		this("");
	}
	
	private void spread(String methodname, ClassInfo classinfo, Map<String, ClassInfo> classinfotable) {
		for (String subclassname : classinfo.subs) {
			if (classinfotable.keySet().contains(subclassname)) {				
				ClassInfo subclassinfo = classinfotable.get(subclassname);
				Set<String> subclassmethods = subclassinfo.methods;
				if (!subclassmethods.contains(methodname)) {
					subclassmethods.add(methodname);
					spread(methodname, subclassinfo, classinfotable);
				}
			}
		}
	}

	public HashMap<String, Set<String>> getTypesToMethods(){
		return this.typesToMethods;
	}
	
	public CallGraph analyze(String... paths) {
		this.allProjectMethods.clear();
		CallGraph callgraph = null;
		this.classDependencies = new HashMap<String, Set<String>>();
		this.typesToMethods = new HashMap<String, Set<String>>();
		try {
			List<JavaClass> allClasses = ClassLocator.loadFrom(paths);
			Map<String, JavaClass> classTable = new HashMap<String, JavaClass>();
			Set<List<String>> staticInvocations = new HashSet<List<String>>();
			for (JavaClass clazz : allClasses) {
				InvocationInstallationBinVisitor visitor = 
						new InvocationInstallationBinVisitor(
								clazz, this.packagePrefix, this.allProjectMethods,
								classTable, staticInvocations);
				visitor.start();
			}
			
			Map<String, ClassInfo> classInfoTable = new HashMap<String, ClassInfo>();
			
			// first pass -- set self, pkg, cls, supers, methods
			for (String classname : classTable.keySet())
				classInfoTable.put(classname, new ClassInfo(classTable.get(classname)));
			
			Set<String> allclassnames = classInfoTable.keySet();
			
			// second pass -- set subs, non-recursively, one level down only for each class
			for (String classname : allclassnames) {
				ClassInfo classinfo = classInfoTable.get(classname);
				for (String superclassname : classinfo.supers) {
					if (allclassnames.contains(superclassname)
							&& !NameHandler.shallExcludeClass(superclassname))
						classInfoTable.get(superclassname).subs.add(classname);
				}
			}
			
			// third pass -- set methods, recursively for all sub levels for each class
			for (String classname : allclassnames) {
				ClassInfo classinfo = classInfoTable.get(classname);
				for (Method method : classinfo.getJavaClass().getMethods()) {
					if (!method.isPrivate()) {
						String methodname = method.getName();
						spread(methodname, classinfo, classInfoTable);
					}
				}
			}
			// fourth pass grab dependencies
			for (String classname : allclassnames) {
				ClassInfo classinfo = classInfoTable.get(classname);
//				System.out.println();
				if (!(this.classDependencies.containsKey(classname))) {
					Set<String> temp = new HashSet<String>();
					this.classDependencies.put(classname, temp);
				}
				//get all referenced classes into table
				for (String rclass : classinfo.classReferences) {
					//Filtering out external classes (libraries) because we assume they will not change.
					// Otherwise we will have to potientially run every test.
					if (allclassnames.contains(rclass)) {
						this.classDependencies.get(classname).add(rclass);
					}
				}
				//get all super classes and interfaces classinfo.supers have immediate parents and interfaces
				for (String pclass : classinfo.supers) {
					//Filtering out external classes (libraries) because we assume they will not change.
					// Otherwise we will have to potientially run every test.
					if (allclassnames.contains(pclass)) {
						this.classDependencies.get(classname).add(pclass);
					}
				}
				//for debugging class dependencies
//				for ( String dependency: this.classDependencies.get(classname)){
//					System.out.println("\nKey: " + classname + " dependency: " + dependency + "\n");
//				}
			}
			//get typesToMethods
			this.calculateTypesToMethods(classInfoTable);

			callgraph = new CallGraph(staticInvocations, classInfoTable);
			
			return callgraph;
		} catch (Exception e) {
			e.printStackTrace();
			System.exit(23);
			return null;
		}
	}

	private void calculateTypesToMethods(Map<String, ClassInfo> classInfoTable) {
		for(String classname : classDependencies.keySet()){
			if(!(this.typesToMethods.containsKey(classname))) {
				this.typesToMethods.put(classname, new HashSet<String>());
			}
			Set<String> nextClasses = new HashSet<String>();
			Set<String> seenClasses = new HashSet<String>();
			ClassInfo classinfo = classInfoTable.get(classname);
			for (String method : classinfo.methods) {
				this.typesToMethods.get(classname).add(classname + ":" + method);
			}
			for( String c : this.classDependencies.get(classname)) {
				nextClasses.add(c);
			}
			while(!(nextClasses.isEmpty())){
				Set<String> currentClasses = nextClasses;
				nextClasses = new HashSet<String>();
				for( String clazz : currentClasses) {
					ClassInfo clazzinfo = classInfoTable.get(clazz);
					if (!(this.typesToMethods.containsKey(clazz))){
						this.typesToMethods.put(clazz, new HashSet<String>());
					}
					for(String method : classinfo.methods) {
						if(clazzinfo.methods.contains(method)) {
							this.typesToMethods.get(clazz).add(classname + ":" + method);
						}
					}
					for( String c : this.classDependencies.get(clazz)) {
						if ( !(seenClasses.contains(c))) {
							nextClasses.add(c);
						}
					}
					seenClasses.add(clazz);
				}
			}
		}

			//for debugging
//			for ( String method: this.typesToMethods.get(classname)){
//				System.out.println("\nKey: " + classname + " method: " + method + "\n");
//			}
	}

	public Set<String> getAllProjectMethods() {
		return allProjectMethods;
	}
	
}
